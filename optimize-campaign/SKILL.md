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

When an implementation is deemed "ready to be tested" (staged, builds cleanly, passes
focused smoke checks), run the **Pre-Testing Local Code Review Gate**: spawn a dedicated
review subagent using `invoke_subagent` following `chromium-code-review` in local mode
(`scripts/pin-local.sh`) with `directives.md` setting `- Mode: local branch` and
`- Skip test coverage: true`. The candidate must achieve a clean PASS review before
advancing to the 32-block remote benchmark.

Every isolated candidate commit is evaluated in pure isolation against baseline
using a **two-stage measurement pipeline**:

1. **Stage 1: Dedicated Bare-Metal Measurement (Exploration & Sizing):**
   Run isolated 32-block balanced ABBA/BAAB runs via `scripts/remote_measure.py` (or local)
   and cycle sizing via `scripts/mechanism_evidence.py`. This verifies cycle reduction, PMU
   counter behavior, and absence of regressions on dedicated hardware with rapid turnaround.

2. **Stage 2: Pinpoint Fleet Validation Gate (Fleet Checkpoint):**
   Candidates demonstrating Stage 1 wins or signal advance to the production hardware fleet
   (default: `mac-m1_mini_2020-perf-pgo`, 150 attempts) using `scripts/pinpoint_measure.py`:
   - **Try CL Policy:** The candidate is uploaded as a lightweight Gerrit try CL (`git cl upload`).
     It is completely acceptable if this initial try CL is NOT a full production implementation
     with feature-specific flags or unit tests; it only needs the isolated optimization logic.
   - **Provenance Tracking:** The Gerrit CL URL and Pinpoint job ID are authoritatively recorded
     with the results in candidate manifests and ledger, serving as the basis for the full
     implementation if the candidate succeeds.
   - **Mandatory Abandonment Rule:** Any try CL that fails the validation gate (stat-sig
     regression, net negative score drag, or candidate rejection) **MUST BE IMMEDIATELY ABANDONED**
     on Gerrit (`pinpoint_measure.py abandon --cl <url>` or `git cl set-close -i <issue>`).
     Unviable experiment CLs must never linger in review queues.

Acceptance uses a dual-path model:
1. **Targeted Improvement (Path A):** Significant in-situ or story-level win on
   the candidate's pre-registered target workload(s) with zero regressions.
2. **Unexpected Real Improvement (Path B):** Significant win on untargeted workload(s),
   provided the cross-cutting mechanism is investigated and understood.
Candidates causing statistically significant regressions on any workload or dragging
down the geometric mean are rejected. When borderline single-story anomalies occur near
the noise floor, run a fast targeted 32-block confirmation on that story
(`--stories=<flagged_story> --blocks=32`) to separate real effects from multiple-comparison noise.

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
3. Maintain authoritative candidate state and metrics in `ledger.json` and export
   clean summaries via `campaign.py status`. Never use untracked shadow ledgers.
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
