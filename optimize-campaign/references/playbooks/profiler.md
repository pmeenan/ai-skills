# Campaign profiler playbook

Goal: two independent, main-thread-scoped, per-story discovery frontiers on
the campaign's rendering surface. Profiles locate work; they do not estimate
score improvement.

Inputs: campaign tip SHA, feature name, campaign display policy, marginal
floor, remote host/source, and output paths for two summaries plus the
reconciliation.

Procedure:

1. Verify a clean campaign tip and an official PGO phase-2 ThinLTO `out/perf`
   build with symbols and frame pointers.
2. Verify the permanent `[SP3_SCORE_TIME]` score-boundary probe is present and
   the legacy outer probe absent. Never patch the remote checkout during capture.
3. Run two independent `remote_measure.py --mode profile` captures with
   `--stories default`, at least 32 repetitions, the campaign flag enabled, and
   the campaign display (the wrapper reads it from the ledger; confirm the
   summary shows `display.mode`, `display.gpu_renderer` and `perf_sampling`).
   The runner samples at a fixed period (875,000 cycles, about 4 kHz per CPU
   at the locked base clock) and the analyzer scopes every story silo to the
   renderer main thread (`--stories-scope main-thread`).
4. Reject a capture unless it reports `interval_kind: exact-scored`,
   `metric_weighting: speedometer-story-v1`, `stories_scope: main-thread`,
   the campaign's display identity, accepted quality, complete inventory,
   matching SHA/features/floor, all 20 default silos, and at least 100
   nominal main-thread samples at the floor in **every** story. A story below
   the floor means more repetitions; never drop the story or lower the gate.
5. Read each story's score-time composition before its frontier: sync versus
   async share, and whether the async phase was CPU-busy or waiting. Record
   stories whose idle fraction is material; those need the latency route, not
   CPU work removal.
6. Generate the reconciliation with `campaign.py profile-scaffold`. Review
   every disposition. Areas are story-qualified; the same symbol hot in two
   stories is two areas. Carry each entry's `platform_sensitivity` flag into
   the reconciliation notes: rendering-backend, font-shaping and
   process-plumbing entries are Pinpoint-first leads, not local candidates.
   Preserve every recurrent source entry; do not combine nested shares or
   remove already-landed residual areas.
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
  "metric_weighting":"speedometer-story-v1",
  "stories_scope":"main-thread",
  "display":{"mode":"x11","display":":1","gpu_renderer":"..."},
  "capture_samples":[0,0],
  "story_count":20,
  "weakest_story_nominal_samples_at_floor":[0,0],
  "stories_with_material_idle_async":["..."],
  "platform_sensitive_entries":0,
  "frontier_count":0,
  "failure":""
}
```

Explicit extended captures with `--stories all` analyze 32 stories and must
report `story_count: 32`; they do not change the default score workload set.
Do not return candidate ceilings or predicted score gains.
