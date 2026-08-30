---
name: optimize-campaign
description: Run long-horizon, evidence-bound Chromium benchmark optimization campaigns through a shared adapter pipeline. Use for campaign planning, profiling, mechanism sizing, guarded implementation, randomized A/B measurement, checkpointing, audit, or adding a Crossbench benchmark such as Speedometer or JetStream. Also use when choosing local versus SSH execution or separating functional characterization from authoritative performance evidence.
---

# Optimize Benchmark Campaign

Use one interlocked campaign pipeline with a small benchmark adapter. Do not
fork the ledger, evidence gates, statistics, reviews, or measurement transport
for each benchmark.

## Start here

1. Identify the requested benchmark and read the reference owned by its thin
   adapter skill: `../optimize-speedometer/references/speedometer3.md` or
   `../optimize-jetstream/references/jetstream3.md`.
2. Read `references/evidence-model.md` before collecting or interpreting
   profiles, counters, or scores.
3. Read `references/execution.md` before selecting local or SSH execution.
4. For an active optimization campaign, read
   `references/campaign-runbook.md` and the role playbook it routes to.
5. Use `scripts/campaign.py` and `scripts/remote_measure.py` as the
   authoritative core entry points.

## Choose a capability

### Initialize and operate a campaign

Initialize with an immutable benchmark identity:

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py init \
  --name jetstream-campaign \
  --benchmark jetstream3 \
  --execution local \
  --branch jetstream
```

The ledger records `benchmark`, `metric_model`, `benchmark_source`, and
`execution`. Later operations resolve those values from the ledger. Never
reinterpret an existing campaign under a different adapter.

The ledger uses Crossbench's word `story` for the generic workload identifier;
it does not imply Speedometer-specific semantics.

### Characterize benchmark integration

Use characterization to verify browser launch, driver compatibility,
Crossbench selection, output parsing, component preservation, and local/SSH
plumbing. Characterization is not performance evidence.

On a local Chromium checkout with an existing development build:

```bash
python3 .agents/skills/optimize-campaign/scripts/remote_measure.py \
  --execution local \
  --characterization \
  --skip-build \
  --mode aa \
  --benchmark jetstream3 \
  --benchmark-source custom \
  --iteration-count 4 --worst-case-count 1 \
  --stories hash-map \
  --browser out/Default/chrome \
  --driver-path out/Default/chromedriver \
  --blocks 2
```

The development build, custom JetStream fork, and small block count each make
this diagnostic-only. Never import the result as a checkpoint.

### Collect authoritative score evidence

Use randomized, balanced ABBA/BAAB blocks, a bare-metal host, release-role
builds, and the benchmark's calibrated campaign policy. The score runner
preserves each page-load repetition as one independent observation.

For JetStream, an online URL is provenance but not an immutable payload.
Authoritative evidence requires `--benchmark-source local` and
`--benchmark-payload-path`; the runner hashes and serves that tree itself on an
ephemeral loopback URL, rechecks it after the run, and binds both facts to the
manifest. The `custom` fork is always investigation-only.

Do not copy Speedometer's block count, duration floor, profile repetitions, or
share floor into a new adapter. Calibrate them with A/A data first, then record
them as campaign policy.

### Profile and size mechanisms

Keep these evidence layers separate:

- exact scored-window profiles locate CPU opportunity;
- instrumented paired counter blocks size a concrete mechanism;
- randomized score A/B establishes benchmark movement.

Profile share is not a score forecast. Internal benchmark iterations are not
independent page-load repetitions.

Speedometer's exact-window profile path is operational. JetStream's score and
component path is operational, while exact-window profile import remains
fail-closed until the existing Crossbench custom-fork marks and
`jetstream_3/perf_sample_span.sql` query are verified end-to-end. Do not fall
back to whole-page timing or silently call an unscored window exact.

### Add another benchmark

Read `references/adapter-contract.md`. Extend the adapter registry and tests,
then update only the benchmark trigger/reference. Keep Chromium as the fixed
platform until a real non-Chromium consumer forces a platform abstraction.

### End-of-campaign reporting and upstream CL preparation

When concluding a campaign:
1. Run an authoritative 32-block full-suite randomized A/B measurement sweep.
2. Generate multi-tab markdown dossiers (`00_OVERALL_CAMPAIGN_REPORT.md` and
   individual optimization write-ups `01_...md` through `NN_...md`) inside the
   active campaign directory (`.agents/campaigns/<campaign-name>/reports/`).
3. Maintain full candidate mapping in `OPTIMIZATION_LEDGER.md` (Opt # -> Git SHA ->
   Candidate Ref -> Subsystem -> Workloads -> Measured Delta -> Upstream Status).
4. Organize banked commits into modular, independent Chromium CL series by
   subsystem, tagged with `TAG=agy` and `CONV=<conversation_id>`.


## Non-negotiable invariants

- One reviewed skill-tree digest covers the core, benchmark triggers,
  adapters, and on-host runners.
- Every artifact names its benchmark, metric model, payload source, and build
  role. Mismatches fail closed.
- Development builds and investigation payloads are characterization only.
- A score component is diagnostic unless the benchmark contract makes it an
  aggregate input. Preserve components; do not substitute one for total score.
- A page-load repetition is the independent statistical unit. Nested
  iterations stay inside that observation.
- Default and available workload sets are distinct adapter facts.
- Local execution never checks out, detaches, or rewrites the working tree.
- SSH execution retains the clean-tree, digest-sync, detached-ref, and host
  lock gates.
- Never claim calibrated JetStream thresholds until A/A data establishes them.

## Ownership boundary

This skill owns the campaign engine, evidence contracts, measurement
transport, analysis tools, detailed runbook, role playbooks, and tests. Thin
benchmark skills own only benchmark semantics, defaults, and adapter-specific
assets. Core code must never import or execute implementation from a benchmark
skill.
