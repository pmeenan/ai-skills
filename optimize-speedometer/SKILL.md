---
name: optimize-speedometer
description: >-
  Run a long-horizon Speedometer 3 optimization campaign in Desktop Chromium
  using exact score-window profiles, score-aware frontier discovery,
  instrumented mechanism counters, paired oracle/candidate cycle evidence,
  bound independent reviews, randomized block A/B checkpoints, and enforced
  reprofile/stopping gates. Also covers one-off Speedometer profiling.
---

# Speedometer 3 optimization campaign

Act as the tech lead. Use scripts for joins, arithmetic, gates, and state.
Agents inspect source and fill bounded artifacts; they do not estimate impact
from intuition and do not manually edit `ledger.json`.

This workflow targets changes whose individual score effect is below the
benchmark noise floor. It deliberately separates three kinds of evidence:

| Question | Authoritative evidence | Never use as a substitute |
| --- | --- | --- |
| Where should we look? | exact-scored, score-weighted cycle profile | flat self-time or an outer suite window |
| Did one mechanism remove work? | counters plus paired baseline/oracle/candidate exclusive cycles | profile share, source inspection, or a typed estimate |
| Did the campaign improve Speedometer? | randomized full-suite block A/B | sum of candidate ceilings |

## Hard invariants

1. `interval_kind` is `exact-scored`. The only admitted intervals are the
   sync and async timers used by Speedometer's score. Outer suite intervals
   are diagnostic and never contribute candidate weight.
2. Profile weights use `speedometer-geomean-v1`: each suite/capture group has
   equal total weight. Raw global cycles overweight slow suites and are not a
   score model.
3. Sampling profiles discover broad areas. They never size a mechanism or
   predict score delta. The default marginal floor is 0.3%, and an analysis
   fails if the floor has fewer than 100 nominal samples.
4. A mechanism reaches `sized` only with a passing artifact emitted by
   `scripts/mechanism_evidence.py`. A candidate reaches review only with a
   passing paired candidate artifact from the same tool.
5. Implement one invariant per opportunity and commit. Do not bundle several
   “squeezes,” adjacent cleanups, or speculative fast paths.
6. A PASS review is bound to the reviewed Git tree and the exact sizing and
   verification artifact digests. Generate its checklist; never hand-author
   an unbound verdict.
7. Reprofile after at most five runtime-changing landings. Record a cumulative
   full-suite checkpoint after at most five landings. `campaign.py` blocks the
   next landing when either artifact is stale.
8. PGO, ThinLTO, symbols, and frame-pointer state are build provenance, not
   assumptions. Profile and release builds must both be official PGO phase 2
   ThinLTO builds. Validate a mechanism in a release-like instrumented twin.
9. Chromium-owned code only. Preserve specification, security, privacy,
   lifecycle, and behavior outside the campaign flag.

If a required field or artifact is unavailable, stop that opportunity. Do
not replace missing evidence with prose.

## Files and roles

| Role | Playbook | Output |
| --- | --- | --- |
| Profiler | `playbooks/profiler.md` | two capture summaries and one reconciled frontier |
| Investigator | `playbooks/investigator.md` | one mechanism, raw counter files, sizing/oracle evidence |
| Implementer | `playbooks/implementer.md` | one staged production diff and candidate raw counters |
| Skeptic | `playbooks/skeptic.md` | bound effectiveness review JSON |
| Adversary | `playbooks/adversary.md` | bound correctness review JSON |
| Measurer | `playbooks/measurer.md` | A/A or A/B summary JSON |

Give each agent its playbook, opportunity id/key, input artifact paths, output
paths, and the instruction to return only the playbook output contract.

The Chromium tree and build directories are exclusive resources. Only the
investigator holding the instrumentation lease or the implementer may dirty
the tree. Reviewers are read-only. Do not run concurrent builds in one output
directory. Verify `git status --porcelain` before transferring the lease.

## Resume or initialize

Work from Chromium `src`.

- If `.agents/campaigns/current/ledger.json` exists, run `campaign.py status
  --print` and resume the recorded gate. Do not recreate state from prose.
- Otherwise confirm the name, branch, target, host, remote source path, and
  skill sync, then initialize:

  ```bash
  python3 .agents/skills/optimize-speedometer/scripts/campaign.py init \
    --name sp3-YYYY-MM --branch speedometer --target 20 \
    --share-floor 0.3 --feature Speedometer3Optimizations \
    --remote-host linux
  ```

Create the feature flag using `resources/flag_scaffolding.md`. On every new
clean-slate campaign, install
`resources/performance_mark_monotonic_probe.patch` as the permanent campaign
probe. It **replaces**, rather than supplements, the legacy outer-window
`[SP3_MONO_TIME]` probe. Existing branches must remove that legacy probe and
install the exact `[SP3_SCORE_TIME]` patch before capturing a frontier. Run
`git apply --check`, compile the patched Blink target with warnings-as-errors,
and run the exact-interval smoke test. The probe intentionally leaks its
thread-local mark buffer, buffers score marks, and flushes outside score
timers. Never apply/remove it around individual remote runs.

Before optimizing, have the measurer run:

1. a fresh-seed, full-suite A/A calibration;
2. a flag-on/off null check on the scaffolding-only commit.

Keep both summary JSON files. Do not proceed if A/A is unstable or the empty
flag has a measurable cost.

Before authorizing a long campaign, run the 3–5-candidate end-to-end pilot in
`resources/instrumented_twin.md`. Continue only when the emitted-counter,
oracle, candidate, and cumulative A/B directions agree.

## Loop

Follow these steps in order. `campaign.py` is the state machine; if a command
rejects an artifact, repair or regenerate it instead of bypassing the gate.

### 1. Capture a fresh frontier

Have the profiler produce at least two independent full-suite captures with
the campaign flag enabled, four repetitions each:

```bash
python3 .agents/skills/optimize-speedometer/scripts/remote_measure.py \
  --mode profile --ref <campaign-tip> --stories all --repetitions 4 \
  --share-floor-pct 0.3 --enable-features Speedometer3Optimizations \
  --summary-out <capture-1.json>
```

Every summary must report:

- `interval_kind: exact-scored`;
- `metric_weighting: speedometer-geomean-v1`;
- accepted quality and at least 100 nominal samples at the floor;
- `stories: all`, matching SHA/features/floor, complete inventory, and unique
  capture/perf/artifact provenance.

Generate and review the reconciliation scaffold, then import it:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py profile-scaffold --capture-summaries <captures.json> \
  --out <reconciliation.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py profile --id <profile-id> --sha <campaign-tip> \
  --areas <reconciliation.json> --capture-summaries <captures.json> \
  --enable-features Speedometer3Optimizations
```

Profile entries are broad discovery areas. Nested stacks overlap; never add
their shares. Exclude wait/idle and payload-only shells. Keep residual work
from already-landed mechanisms visible until a follow-on profile shows it
below the floor.

### 2. Decompose one area

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py next --count 3
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <discovery> --to investigating
python3 .agents/skills/optimize-speedometer/scripts/campaign.py decompose-scaffold --opp <discovery> --out <paths.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py decompose --opp <discovery> --children <paths.json>
```

Each novel path has one stable `component/strategy` mechanism key and one
testable invariant. “Make function faster” is not an invariant. Reuse known
keys; do not retry landed, rejected, or reverted mechanisms without genuinely
contradictory new evidence. Follow the exactly-one-primary and `covered-by`
rules in `resources/decomposition.md`.

### 3. Instrument and size the mechanism

The investigator adds temporary flag-controlled counters to a release-like
instrumented twin. Emit one row per repetition/suite inside each block (at
least all 32 suites); the reducer gives every row equal score weight. Count at
minimum in each row:

- calls and applicable calls;
- exclusive mechanism cycles;
- avoidable exclusive cycles, identified by a dual-path counter or oracle;
- total cycles inside the exact scored intervals;
- blocks independently, never one aggregate run.

Use `resources/instrumented_twin.md` for the build/probe/emission recipe and
`resources/mechanism_evidence.md` for exact field meanings.

Classify the work as `score-critical` or `cpu-only` using a digested trace
artifact. Raster/GPU/worker work is not score-critical merely because it is
on-CPU during an outer suite window.

Generate metadata, replace only its `REPLACE` fields, and machine-ingest the
harness logs. Never type or paste counter rows into JSON:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py scaffold --opp <id> \
  --mechanism-key <component/strategy> --profile-id <profile> \
  --variant baseline --out <baseline.metadata.json>
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py ingest \
  --metadata <baseline.metadata.json> --log <block-1.log> --log <block-2.log> \
  --log <block-3.log> --out <baseline.raw.json>
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py summarize \
  --raw <baseline.raw.json> --out <sizing.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <id> --to sized \
  --evidence-manifest <sizing.json>
```

The stored bound is an upper confidence bound on avoidable scored CPU-cycle
share, not a predicted score delta. Use at least three blocks. Record full build identity, GN-args digest,
toolchain id, PGO-profile digest, probe revision, probe A/A overhead, and the
trace digest. Probe A/A overhead above 1% fails the artifact.

When feasible, implement an intentionally incorrect oracle that bypasses only
the proposed work. Compare it with the same blocks:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py compare --kind oracle \
  --baseline <baseline.raw.json> --variant <oracle.raw.json> \
  --out <oracle.json>
```

An oracle is a ceiling, not permission to change semantics. Reject the path
if applicability is low, the oracle does not remove exclusive cycles, or the
work is off the scored critical path and no CPU-only goal justifies it.

### 4. Implement and verify exactly one invariant

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <id> --to implementing
```

The implementer preserves the temporary counters while developing, runs
targeted correctness tests, and repeats the same blocks with
`variant: candidate`. Validate the paired reduction:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py compare --kind candidate \
  --baseline <baseline.raw.json> --variant <candidate.raw.json> \
  --out <candidate.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <id> --to review --tests <test-summary> \
  --verification-manifest <candidate.json>
```

The lower 95% confidence bounds for both relative exclusive-cycle reduction
and net scored-cycle share saved must be positive. Inspect
`total_scored_cycle_change_ci95_pct`; a `moved_work_warning` cannot be called
net work removal without resolving where total work moved. Remove temporary
probes from the staged production diff unless the instrumentation is an
intentional, reviewed product metric.

### 5. Run bound reviews

For each role, generate the report after entering review:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review-scaffold --opp <id> --role skeptic \
  --out <skeptic.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review-scaffold --opp <id> --role adversary \
  --out <adversary.json>
```

Reviewers inspect the staged diff and the raw artifacts referenced by their
digests, set every bounded check to JSON `true` only when verified, add
findings, and set the verdict. Record it:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review --opp <id> --role skeptic --verdict PASS \
  --report <skeptic.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review --opp <id> --role adversary --verdict PASS \
  --report <adversary.json>
```

A PASS requires all checks true and no findings. A FAIL returns to one of at
most two rework rounds or rejects the mechanism.

### 6. Land, checkpoint, and reprofile

Commit the exact reviewed tree and record it:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <id> --to landed --commit <sha>
```

After at most five landings, run a cumulative full-suite flag A/B with a fresh
recorded seed and at least five balanced ABBA/BAAB blocks. Prefer 10–15 blocks
when the current MDE is larger than the expected batch effect. Record the
machine output, not copied numbers:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py checkpoint --summary <remote-ab-summary.json>
```

Also reprofile the enabled campaign tip after at most five runtime changes,
and immediately after two candidate verification misses or a checkpoint that
does not move in the expected direction. Downstream mechanisms must be sized
against the residual profile, not a stale baseline.

When all child paths of a discovery are terminal, generate and record the
digest-bound skeptic exhaustion review, then run `campaign.py exhaust` as
shown in `resources/decomposition.md`. Unbound discovery prose cannot retire
profiled work.

## Stop rules

Stop and report when any condition holds:

- an exact-scored capture or build provenance cannot be produced;
- A/A or empty-flag calibration fails;
- a persistent regression survives confirmation and bisect;
- three consecutive mechanisms fail the machine evidence gate;
- the fresh enabled frontier is exhausted under `campaign.py audit-exhaustion`;
- the human target is met with a sufficiently powered full-suite A/B.

Do not claim an aggregate improvement when the confidence interval crosses
zero. Report the point estimate, 95% CI, MDE, blocks, seed, SHAs, and build
provenance.

## One-off profiling

For discovery only, run `remote_measure.py --mode profile` as above and read
`candidate_frontier.md` plus `resources/analyzer_reference.md`. Do not use a
one-off profile share as an optimization forecast.
