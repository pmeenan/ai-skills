# Benchmark adapter contract

Load this reference when adding or reviewing a benchmark adapter.

An adapter owns only benchmark semantics:

- canonical id, Crossbench name, and result filename;
- metric-model id and whether workload scalars are higher- or lower-is-better;
- default and available workload-set identity;
- Crossbench payload/source arguments;
- suite-score and per-workload extraction;
- diagnostic component extraction;
- score versus investigation payload classification;
- exact-interval source and fidelity, when implemented.

Campaign policy owns empirically chosen repetitions, blocks, duration floors,
minimum detectable effects, and profile sample/share floors. Do not freeze
those as benchmark identity before calibration.

Every parser must reject aggregate Crossbench JSON as an independent run. It
must accept only a per-run scalar suite score, positive finite workload
scalars, and optional positive finite diagnostic components.

The shared statistics contract is a sign-normalized log delta: positive means
arm B is better. Suite scores are higher-is-better. Per-workload values may be
higher-is-better scores (JetStream) or lower-is-better times (Speedometer).

Adapter additions require tests for aliases, command construction, per-run
versus aggregate parsing, suite score, workload values, components, direction,
payload classification, and workload-set counts.
