# Campaign profiler playbook

Goal: produce a complete, recurrent per-story discovery frontier. Profiles
locate broad areas inside each story silo; they do not estimate score
improvement.

Inputs: campaign tip SHA, feature name, marginal floor, remote host/source,
and output paths for two summaries plus the reconciliation.

Procedure:

1. Verify a clean campaign tip and an official PGO phase-2 ThinLTO build.
2. Verify the permanent `[SP3_SCORE_TIME]` score-boundary probe is present and
   the legacy `[SP3_MONO_TIME]` outer probe is absent. On a clean campaign the
   tech lead installs and compiles the exact patch before this step. Never
   patch the remote checkout during capture.
3. Run two independent `remote_measure.py --mode profile` captures with
   `--stories all`, at least 16 repetitions, and the campaign flag enabled.
   One full-suite run collects every story; the analyzer then decomposes it
   into 32 independent story silos (`analysis/stories/<story>/`), each
   analyzed in isolation with shares relative to that story's scored cycles.
4. Reject either capture unless it reports `interval_kind: exact-scored`,
   `metric_weighting: speedometer-story-v1`, accepted quality, complete
   inventory, matching SHA/features/floor, all 32 story silos analyzed, and
   at least 100 nominal samples at the local floor in **every** story silo.
   A story below its sample floor means the capture needs more repetitions;
   rerun the capture rather than dropping the story.
5. Generate the reconciliation with `campaign.py profile-scaffold`. Review
   every disposition. Areas are story-qualified: the same symbol hot in two
   stories is two independent areas, each ranked by its own local story
   share. Preserve every recurrent source entry; do not combine nested
   shares, merge across stories, or remove already-landed residual areas.
6. Import with `campaign.py profile`. Do not hand-edit ledger state. The
   ledger's global ranking orders every discovery by its impact on its own
   target story; do not rescale local shares to full-suite percentages.

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
  "capture_samples":[0,0],
  "story_count":32,
  "weakest_story_nominal_samples_at_floor":[0,0],
  "frontier_count":0,
  "failure":""
}
```

Do not return candidate ceilings or predicted score gains.
