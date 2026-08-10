# Mechanism evidence schema

Always start with `mechanism_evidence.py scaffold`; do not author the shape
from memory. Fill metadata only, then run `mechanism_evidence.py ingest` over
the `[SP3_CYCLE_ROW]` logs emitted by `cycle_profiler.h`. The reducer owns the
`blocks`, `counter_logs`, and `ingested_by` fields. Hand-entered blocks fail.

Each raw file describes one variant (`baseline`, `oracle`, or `candidate`) of
one opportunity and profile. It binds:

- exact score scope and a digested trace used to classify criticality;
- complete release-like build identity (SHA, binary id, GN args, toolchain,
  and PGO profile), bound to a digested provenance artifact;
- probe revision and measured A/A overhead, bound to its A/A artifact;
- at least three independent blocks;
- inside every block, one `repetition|suite` row for all 32 Speedometer suites.

Each log is SHA-256 bound. Ingestion rejects missing/failed perf events, zero
calibration, invalid reads, thread-affinity or nesting violations, and a PMU
time-running/time-enabled ratio below 0.99. See `instrumented_twin.md` for the
build and emission recipe.

Group fields are raw harness output:

| Field | Meaning |
| --- | --- |
| `calls` | Entries to the measured mechanism in this exact score group |
| `applicable_calls` | Entries where the proposed invariant is true |
| `exclusive_cycles` | Cycles in the smallest instrumented work region |
| `avoidable_cycles` | Exclusive cycles specifically avoidable under the invariant, established by a dual-path counter or oracle |
| `total_scored_cycles` | On-CPU cycles in this exact score group |

The reducer computes a cycle share inside each group, then equally averages
groups. It never pools raw cycles across suites. `summarize` reports an upper
95% confidence bound on avoidable score-weighted CPU-cycle share. `compare`
uses exactly matching block and group identities and requires positive lower
95% confidence bounds for both relative exclusive-cycle reduction and net
score-weighted cycle share saved.

`compare` also reports the paired log-ratio change in `total_scored_cycles`
with a 95% CI. This uses the baseline total as the saved-share denominator, so
adding work cannot inflate the apparent mechanism saving. A
`moved_work_warning` is skeptic evidence that total scored work increased; it
does not automatically fail a noisy candidate, but it must be explained or
resolved before `net_work_removed` can pass.

These are mechanistic CPU results, not Speedometer score predictions. The
aggregate score verdict still comes from randomized block A/B.
