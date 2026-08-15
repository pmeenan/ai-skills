# Profiler playbook

Goal: produce a complete, recurrent discovery frontier. Profiles locate broad
areas; they do not estimate score improvement.

Inputs: campaign tip SHA, feature name, marginal floor, remote host/source,
and output paths for two summaries plus the reconciliation.

Procedure:

1. Verify a clean campaign tip and an official PGO phase-2 ThinLTO build.
2. Verify the permanent `[SP3_SCORE_TIME]` score-boundary probe is present and
   the legacy `[SP3_MONO_TIME]` outer probe is absent. On a clean campaign the
   tech lead installs and compiles the exact patch before this step. Never
   patch the remote checkout during capture.
3. Run two independent `remote_measure.py --mode profile` captures with
   `--stories all`, at least four repetitions, and the campaign flag enabled.
4. Reject either capture unless it reports `interval_kind: exact-scored`,
   `metric_weighting: speedometer-geomean-v1`, accepted quality, complete
   inventory, matching SHA/features/floor, and at least 100 nominal samples at
   the floor.
5. Generate the reconciliation with `campaign.py profile-scaffold`. Review
   every disposition. Preserve every recurrent source entry; do not combine
   nested shares or remove already-landed residual areas.
6. **Per-Benchmark Story Breakdown:** Decompose stacks for each of the 32 individual
   stories using the exact per-suite `measurement_intervals` down to a **$0.3\%$ local
   story marginal share floor**. Aggregate all discovered hotspots into the unified
   Master Ranked Frontier sorted by projected global geomean impact.
7. Import with `campaign.py profile`. Do not hand-edit ledger state.

Return only:

```json
{
  "verdict":"PASS|FAIL",
  "profile_id":"...",
  "sha":"...",
  "capture_summaries":"absolute path",
  "reconciliation":"absolute path",
  "interval_kind":"exact-scored",
  "metric_weighting":"speedometer-geomean-v1",
  "capture_samples":[0,0],
  "nominal_samples_at_floor":[0,0],
  "frontier_count":0,
  "failure":""
}
```

Do not return candidate ceilings or predicted score gains.
