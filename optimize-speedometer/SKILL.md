---
name: optimize-speedometer
description: Optimize Chromium against Speedometer 3 through the shared evidence-bound optimization-campaign pipeline. Use for Speedometer Crossbench setup, exact scored-window profiles, story-level frontier discovery, mechanism evidence, randomized score A/B checkpoints, or a full Speedometer optimization campaign.
---

# Optimize Speedometer

Use this as the thin Speedometer adapter entry point for
`../optimize-campaign`. The campaign engine, measurement transport, evidence
tools, reviews, and ledger are owned by that shared skill.

## Required reading

1. Read `../optimize-campaign/SKILL.md`.
2. Read `references/speedometer3.md`.
3. Read `references/discarded-candidates/INDEX.md` and the relevant subsystem
   file before proposing or investigating opportunities to avoid repeating
   previously invalidated hypotheses.
4. Load the shared detailed runbook, evidence model, execution reference, or
   role playbook only when the current campaign operation needs it.

## Adapter defaults

- Adapter: `speedometer3`
- Crossbench benchmark: `speedometer_3.1` (matches Pinpoint `speedometer3`)
- Default workloads: 20 stories (`--stories=default`, matching Pinpoint)
- Available workloads: 32 stories (`--stories=all`, explicit extended coverage)
- Suite score: `Score`, higher is better
- Story scalar: total story time, lower is better
- Metric model: `speedometer-story-v1`
- Pinned payload: Chromium `third_party/speedometer/v3.1`
- Local functional build: `out/Default/chrome` with the matching
  `out/Default/chromedriver`

All commands use the shared core entry points. For example:

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py init \
  --name speedometer-campaign \
  --benchmark speedometer3 \
  --execution local \
  --branch speedometer --baseline <full-sha> \
  --display :1 --display-vt 9 --pause-service ollama
```

Then two separately timed A/A sessions and `campaign.py calibrate`; the
per-story MDEs it records set the qualification floors for the whole campaign.

Use `out/Default` only for functional characterization. Authoritative score
or mechanism evidence must satisfy the release-role build and calibrated
campaign policy defined by the core runbook.

## Speedometer-only invariants

- Exact scored windows are the sync and async timers used by Speedometer's
  score; an outer suite interval is diagnostic.
- Discovery analyzes each story's renderer main thread in isolation and keeps
  story-qualified frontier identities. Combine shared mechanisms across stories
  only with causal score bounds; raw CPU-share aggregation is diagnostic.
- Profiles, mechanism captures and score runs share one rendering surface
  (GPU-backed X display); headless SwiftShader profiles rank canvas and raster
  work the Mac M1 fleet never executes on the main thread.
- The monotonic-mark probe is a Speedometer adapter asset at
  `../optimize-campaign/assets/speedometer3/performance-mark-monotonic-probe.patch`.
- Speedometer-calibrated repetition, duration, marginal-share, and checkpoint
  thresholds must not be copied into another benchmark adapter.
