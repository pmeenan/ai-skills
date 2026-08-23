# JetStream 3 benchmark semantics

Load this reference for any JetStream campaign or adapter change.

## Workload sets

Crossbench exposes 94 available workloads. The standard JetStream 3 selection
contains 77 workloads tagged `default`. `--stories=default` and
`--stories=all` are not interchangeable. Record the selector and observed
workload names in every artifact.

## Statistical unit

One Crossbench repetition/page load is one independent observation. JetStream's
`--iteration-count` repeats a test inside that page and contributes to the same
observation. Never count internal iterations as independent score samples.

## Result model

The per-run scalar result file is `jetstream_3.0.json`.

- `Total/Score` is the suite score.
- `<workload>/Score` is a workload score.
- Other `<workload>/<component>` values are diagnostics and must be preserved.

Common components include First, Worst, and Average. Some workload families use
different semantics such as MainRun and Stdlib. Do not impose one component
formula on every workload; Crossbench and the benchmark payload own score
calculation.

Suite and workload scores are higher-is-better. The shared runner computes
positive deltas when arm B increases them.

## Payloads

- `custom`: Chromium-hosted fork with extra controls and user-timing marks;
  investigation only.
- `live`: Chromium-hosted standard workload; useful for compatibility checks,
  but remote content is mutable.
- `official`: browserbench.org payload; also mutable from the evidence
  pipeline's perspective.
- `local`: pinned payload tree. For authoritative evidence, provide the tree
  to the runner; it binds a SHA-256 tree digest, serves it on an ephemeral
  loopback URL, and verifies the digest again after measurement.

Crossbench revision, URL choice, and payload digest are separate provenance
facts. Record all applicable facts.

## Exact intervals

The custom fork provides workload/iteration user-timing measures. Chromium's
Crossbench tree includes
`crossbench/probes/trace_processor/queries/jetstream_3/perf_sample_span.sql`,
which maps measures to workload and First/Worst/Average labels. It is currently
disabled by a TODO in the V8 team probe preset. Treat it as an implementation
lead, not verified evidence, until an end-to-end capture proves:

- all selected scored workloads have intervals;
- no unmatched, overlapping, or unscored intervals enter the profile;
- WebAssembly special cases map correctly;
- page-load repetitions remain separable;
- the imported component labels agree with the scalar result artifact;
- profiling overhead passes a calibrated A/A budget.
