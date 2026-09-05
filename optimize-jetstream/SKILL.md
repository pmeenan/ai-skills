---
name: optimize-jetstream
description: Optimize Chromium against JetStream 3 through the shared evidence-bound campaign pipeline. Use for JetStream Crossbench setup, local characterization, score/component parsing, workload selection, payload provenance, A/A calibration, randomized A/B campaigns, or planning exact-window JetStream profiling.
---

# Optimize JetStream

Use this as the thin JetStream trigger for `../optimize-campaign`.

## Required reading

1. Read `../optimize-campaign/SKILL.md`.
2. Read `references/jetstream3.md`.
3. Load the core evidence, execution, or adapter reference when that capability
   is needed.

## Defaults

- Adapter: `jetstream3`
- Crossbench benchmark: `jetstream_3.0`
- Standard suite selector: `default` (77 enabled workloads)
- Available selector: `all` (94 workloads, including disabled/nonstandard
  entries)
- Metric model: `jetstream-workload-score-v1`
- Local functional build: `out/Default/chrome` with matching
  `out/Default/chromedriver`
- Investigation payload: Crossbench `--custom`
- Score payloads: `--live`, `--official`, or a pinned local payload;
  authoritative evidence requires the last option; the runner hashes and
  serves it on loopback

## First-run characterization

Run one small workload through the shared local path. Use AA so no unregistered
feature flag is required. The result proves integration only, even though the
benchmark emits numeric scores.

```bash
python3 .agents/skills/optimize-campaign/scripts/remote_measure.py \
  --execution local --characterization --skip-build \
  --mode aa --blocks 2 \
  --benchmark jetstream3 --benchmark-source custom \
  --iteration-count 4 --worst-case-count 1 \
  --stories hash-map \
  --browser out/Default/chrome \
  --driver-path out/Default/chromedriver
```

After characterization, calibrate page-load repetitions and block noise before
setting campaign policy. Do not reuse Speedometer's thresholds.

## Campaign capability boundary

Score/component parsing and immutable-payload characterization are available.
Exact-window profile import and the authenticated fleet contract remain blocked
until JetStream-specific trace, workload and calibration semantics are verified
end-to-end. Do not initialize a full admission campaign by substituting
Speedometer thresholds or treating whole-page CPU samples as exact windows.
See [README.md](README.md) for start/resume prompts appropriate to this stage.
