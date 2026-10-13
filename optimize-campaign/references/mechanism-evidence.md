# Shared mechanism evidence schema

Always start with `mechanism_evidence.py scaffold`; do not author the shape
from memory. Fill metadata only, then run `mechanism_evidence.py capture` for
each block and pass its manifests to `ingest`. The capture runner owns the
nonce, Crossbench command, raw browser logs, and extracted counter log. The
reducer owns `blocks`, `capture_manifests`, `counter_logs`, and `ingested_by`.
Hand-entered rows or manifests without matching raw browser output fail.

Each raw file describes one variant (`baseline`, `oracle`, or `candidate`) of
one opportunity and profile, measured against the mechanism's single
`target_story`. It binds:

- the target story (sizing and verification run only that story via
  `--stories=<target_story>`; shares are local to its scored cycles);
- the campaign's minimum avoidable-share lower-bound floor (default 0.3%);
- exact score scope and a digested trace used to classify criticality;
- complete release-like build identity (SHA, binary id, GN args, toolchain,
  and PGO profile), bound to a digested provenance artifact;
- probe revision and measured A/A overhead, bound to its A/A artifact;
- at least three independent blocks with natural run variance;
- inside every block, one `repetition|story` row per repetition of the target
  story, with at least 4 repetitions per block (default 10).

Each log is SHA-256 bound to a staged source tree, real browser binary, fresh
capture nonce, and the target story's exact-score mark inventory. Ingestion rejects
placeholder suite names, repeated synthetic score totals, missing/failed perf events, zero
calibration, invalid reads, thread-affinity or nesting violations, and a PMU
time-running/time-enabled ratio below 0.99. See `instrumented_twin.md` for the
build and emission recipe.

Temporary probes are represented by a `bind-instrumentation` receipt. It
reapplies one digest-bound instrumentation patch in a temporary Git index and
proves `product_tree + patch = source_tree`. Baseline and candidate must have
different product trees, binaries, and executable `.text` sections but the
same instrumentation patch revision. Debug-only or compiler-erased changes
therefore fail. Review binds to candidate `product_tree`, so probes can be
removed without severing the measurement provenance.

Instrumentation overhead is also reducer-owned. Run an uninstrumented-A versus
instrumented-B full-suite binary `ab2`, then use `calibrate-aa`; metadata may
only reference that digest-bound artifact. Its upper 95% confidence bound must
not exceed 1%.

Build identity is runner-owned too: on the bare-metal host, `provenance` runs
the instrumented Chrome `autoninja` rebuild itself and records its output,
host boot/CPU/kernel, staged tree, browser SHA, ELF build-id, executable
`.text`, GN args, bundled toolchain, and exact PGO profile;
`attach-provenance` copies that artifact into a metadata skeleton. Do not
hand-author the build object.

Group fields are raw harness output:

| Field | Meaning |
| --- | --- |
| `calls` | Entries to the measured mechanism in this exact score group |
| `applicable_calls` | Entries where the proposed invariant is true |
| `exclusive_cycles` | Cycles in the smallest instrumented work region |
| `avoidable_cycles` | Exclusive cycles specifically avoidable under the invariant, established by a dual-path counter or oracle |
| `total_scored_cycles` | On-CPU cycles in this exact score group |

The reducer computes a cycle share inside each repetition group, then equally
averages the repetitions of the target story. It never pools raw cycles
across repetitions. `summarize` reports an upper 95% confidence bound on the
avoidable CPU-cycle share of the target story's scored cycles. `compare`
uses exactly matching block and group identities and requires positive lower
95% confidence bounds for both relative exclusive-cycle reduction and net
target-story cycle share saved.

`compare` also reports the paired log-ratio change in `total_scored_cycles`
with a 95% CI. This uses the baseline total as the saved-share denominator, so
adding work cannot inflate the apparent mechanism saving. A
`moved_work_warning` is skeptic evidence that total scored work increased; it
does not automatically fail a noisy candidate, but it must be explained or
resolved before `net_work_removed` can pass.

These are mechanistic CPU results, not Speedometer score predictions. The
aggregate score verdict still comes from randomized block A/B.

## Oracles vs. Perfect-Knowledge Ceilings, 1-Block Smoke Tests, and Diagnostic A/Bs

- **Separate perfect-knowledge ceiling from pre-call predictor design (`#411`, `#414`, `#416`):** An oracle that computes a realistic pre-call cache key or predicate measures the viability of that specific design, *not* the mechanism's ceiling. Always establish a perfect-knowledge ceiling first (via a post-hoc twin counter or a two-pass record/replay oracle that knows which calls produce identical outputs) before or alongside testing a pre-call predictor, and report headroom (ceiling) separately from predictor coverage/viability (`#411`, `#414`, `#416` in `r197`).
- **1-block smoke test before 8-block sizing:** Before launching an 8-block paired twin sizing run (`mechanism_evidence.py`) or a multi-block oracle run, always run a 1-block smoke test (`--repetitions=10`) on the target story and inspect the emitted `[SP3_REDUNDANCY_ROW]` / `[SP3_MECHANISM_TRACE]` counters (`fired > 0`, `audit_mismatch == 0`, expected `active_vt`). In `r197`, a 1-block smoke across 5 oracles (`#411`, `#415`, `#416`, `#414`, `#412`) caught that `#416`'s hook sat inside a layout entry point already skipped by `PositioningPortal`'s `SkipRelayoutIfSameConstraintSpace` before any 8-block sizing time was spent.
- **Diagnostic isolation A/B when a bundled candidate regresses a story:** When a mechanism bundles two sub-optimizations and shows a target-story win alongside an unexpected regression on another story (`r128`/`r129`/`r130` on `#284`), run short 24–32 block diagnostic A/Bs isolating each sub-mechanism on the affected stories. In `#284`, isolating `reuse-only` (`-0.40%` on `Editor-TipTap`) from `curly-only` (`+3.54%` on `Editor-TipTap`, neutral on `TodoMVC-Svelte-Complex-DOM`) turned an `INCONCLUSIVE` bundled patch into a clean landed win (`+3.83%` target story, `+0.178%` full suite).
