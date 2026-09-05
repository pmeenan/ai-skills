# Measurement and opportunity policy

This policy governs new campaigns. An active campaign remains bound to its
recorded skill digest, display policy and calibration epoch; finish or stop
its current run before adopting a new reviewed skill revision. Never relabel
old data or fork a replacement ledger to pass a gate.

## One rendering surface for everything

Speedometer scores renderer main-thread wall time, and what runs on that
thread depends on the rendering backend. Headless Chrome renders through
SwiftShader: canvas flushes rasterize on the main thread and tiles raster on
CPU workers, none of which happens on the Mac M1 PGO fleet bot. So:

- `campaign.py init` freezes a display policy (`headless`, or an X display
  such as `:1` with its console VT). Discovery profiles, mechanism captures
  and every score run use it; runners record mode, display, viewport and the
  browser's GPU renderer string, and the campaign refuses imports from a
  different surface or from a software renderer on an X display.
- A/A calibration compares the surface as part of the stable identity.
- Frontier entries in rendering, font-shaping and process-plumbing code are
  flagged `platform_sensitivity`; treat them as leads that need Pinpoint on
  the Mac bot before any host time, not as local wins.

## Calibration sets the floors

Two separately timed A/A sessions on the campaign surface go through
`campaign.py calibrate`. For the suite and every story, the null point
estimate must sit inside the tolerance band (bias), the 80%-power MDE must
stay under the cap (precision), and the family-adjusted interval must contain
zero; a wide but unbiased story is not a failure, its MDE simply raises its
floor. The command records each story's MDE, and from then on:

    qualification floor(story) = max(share floor, 2 × MDE(story))

The floor applies to a proposal's estimated target-story impact at
`decompose` and to the sizing lower bound at `advance --to sized`. A mechanism
that cannot plausibly move its story by twice the story's MDE cannot be read
by the fixed-plan measurement, so implementing it only spends host time. On
the Linux box story MDEs at 32 blocks run from about 0.2% to 2%, which makes
the practical floor roughly 1% to 4% of a story; the old 0.3% floor admitted
work ten times below what any run could confirm.

## Discovery: main thread, wall time, and why the work runs

Story silos rank renderer main-thread samples inside exact scored intervals.
Other threads and processes (concurrent compilation, compositor, raster
workers, browser networking) are visible in the diagnostic full view only;
they were half the samples in earlier captures and produced most of the junk
discoveries. Each silo needs 100 nominal samples at the floor; fix that with
repetitions (32) and the fixed-period 4 kHz sampling, never by lowering the
gate.

Every story report opens with its score-time composition: sync versus async
wall time and, from the samples, how busy the main thread was in each. On
this host the async phase is CPU-bound frame work (style, layout, paint,
commit under `BeginMainFrame`), so CPU discovery covers it; where a story
shows real idle time, the trace-backed latency route applies.

Investigate top-down. For an expensive parent, ask in order: can the whole
subtree be skipped under a checkable condition; is the same result computed
again for an input already seen; can the representation or algorithm change;
and only then is the leaf tight. The first two are the only shapes among the
historical suite-level wins, and they are measurable before any code is
written: the redundancy probe counts, inside the scored window, how many
times the site runs per step, how often the invariant holds, and how often
the input repeats. A Layer 1/2 proposal must cite that packet, and its
avoidable fraction may not exceed what the counts support.

State: condition C occurs in X/Y measured calls; it permits removing exactly
W, including named descendants, while preserving observable behavior B.
Measure applicable and non-applicable calls, added checks, invalidation and
cold paths. A perfect oracle bounds a mechanism; it is never a shippable
result. Keep CPU shares as CPU shares; a score forecast requires a paired
oracle or a validated critical-path counterfactual, recorded as an
`opportunity_budget` with measured causal bounds:

```json
{
  "suite_workload_count": 20,
  "workloads": [{"name": "Charts-chartjs", "basis": "paired-oracle",
    "score_gain_upper_pct": 2.0, "artifact_sha256": "<raw evidence digest>",
    "source_revision": "<full commit>"}],
  "confidence": 0.5, "acceptance_probability": 0.8,
  "engineering_hours": 4, "measurement_hours": 3,
  "calibrated_mde_pct": 0.1, "minimum_effect_pct": 0.05
}
```

Give each investigation a finite budget. A legitimate
`no-qualifying-mechanism` decomposition carries an `investigation` packet
(`source_revision`, `hypotheses`, `falsifications`, `budget_used`,
`stop_reason`); it closes that bounded search, not the subsystem. Historical
rejections are hypotheses to understand, not prohibitions.

## Two causal evidence routes

**Work removal:** paired, symmetrically instrumented scopes with measured
applicability and the same thread scope in numerator and denominator. The
reducer reports the mechanism's saved share of the story's scored cycles, not
net savings; a significant increase in total scored cycles blocks the gate.

**Latency reduction:** `latency_evidence.py --packet ... --out ...` with
trace-bound baseline/candidate blocks, balanced `AB`/`BA` order, native trace
events and flow edges, and `interval_kind: exact-scored`. Thread order alone
does not prove a dependency; a changed path must preserve the observable
dependency and the benchmark's completion semantics. This route needs the
same uninstrumented score gates.

## Fixed-plan decisions

Register an attempt before launch, including cancelled and failed ones.
Freeze candidate and baseline commits, payload digest, workload inventory,
activation, primary endpoint, sample count, confidence level, minimum useful
effect and regression margins. Balanced randomized ABBA/BAAB blocks are the
independent unit; browser iterations are not.

`statistics_policy.py` makes four outcomes explicit: INVALID, INCONCLUSIVE,
REGRESSION, IMPROVEMENT. Intervals operate on block log deltas; the
regression family is every workload plus the aggregate under Bonferroni
bounds. The runner's manifest applies the same family to its story flags:
`stat_sig_story_regressions` and `stat_sig_story_improvements` are adjusted,
`unadjusted_story_flags` are diagnostics, and the manifest states how many
unadjusted flags a null run produces. Neither list authorizes a selective
rerun. Choose the primary before seeing data; an unexpected win is a new
hypothesis for a separately registered confirmation.

## Host policy inside a session

The tuner owns the session: no turbo, performance governor, min = max = base
frequency, NMI watchdog off, SMT off, console VT switched to the benchmark X
server, optional GPU clock lock, and the campaign's `pause_services` (other
GPU tenants such as an LLM server) stopped; everything is restored in reverse
and verified. Score and profile runs keep ASLR enabled so per-repetition layout
randomization averages out alignment luck; cycle-probe captures disable it
for stable addresses. Per-block observations record frequency, thermal
throttle counters, active VT, GPU clocks and foreign GPU compute processes; a
throttle event, VT change or a foreign GPU process starting mid-run
invalidates the run.

Keep controlled discovery measurements separate from production-like
measurements. Record OS, architecture, display mode, viewport, GPU renderer
and fleet bot; matching workloads does not make Linux and a Mac Pinpoint bot
identical, and the Mac M1 PGO bot is the validation reference.

## Landing evidence

Landing takes runner-owned evidence, not signatures: one or more local
fixed-plan A/B manifests from `run_ab_benchmark.py` (recomputed from their
raw block results at import, digest-bound, both arms built from the same
full candidate commit on the campaign surface) and a Pinpoint analysis
summary from `pinpoint_measure.py` for the campaign's fleet bot (Mac M1 PGO
by default). The fixed plan is frozen at init (`statistics` in the ledger)
with the minimum useful effect raised to the calibrated MDE of the primary
stories; the primary for a candidate is its target story, the regression
family is every story plus the suite. An unexpected win needs a second,
separately seeded local run that confirms it. `audit` re-checks every
receipt digest and the isolated-to-integrated patch mapping. Same-user
digests and Git history are consistency checks, not authentication against
a fabricated manifest; the transcript remains the audit trail for that.
