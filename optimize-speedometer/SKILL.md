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
per-story MDEs it records set the qualification floors for the whole campaign,
and `campaign.py profile` refuses to import before they exist. After the two
profile captures, run `story_lens.py` on both and import it with
`profile --lens`; the Speedometer-specific reading of the lens is in
`references/speedometer3.md`.

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

### Discarded Candidate Catalog Check (Before Proposing a Mechanism)

Before proposing any `novel` or `algorithmic` mechanism in a decomposition, investigators must check [references/discarded-candidates/INDEX.md](references/discarded-candidates/INDEX.md) and the machine-readable catalog `references/discarded-candidates/discarded-candidates.json` (which combines earlier discarded ideas with all 43 rejected/parked entries from `speedometer-september`). `campaign.py decompose-draft`, `campaign.py decompose`, and `precheck_decomposition.py` automatically emit a non-fatal `WARNING:` when a proposed `novel`/`algorithmic` mechanism key or anchor function matches a discarded entry. Because a mechanism that failed on one story or under an earlier implementation might still apply under different constraints, the match is a warning rather than a hard refusal — the investigator must read the prior failure mode and document why the new proposal avoids it.

### No Benchmark Special-Casing (`#415` Component A)

Designs that pattern-match page JavaScript source strings or Speedometer's framework code shape (such as `#415` Component A matching Preact's `if (oldValue === newValue) return;` setter wrapper) are disallowed and cannot be used to clear qualification floors or land.

### Console VT Ownership (`--vt 9`) on X11 Measurement Hosts

Every `tune_benchmark_host.py enable` invocation for X11 runs (`--display :1`), including manual or custom probe/diagnostic scripts, **must** pass `--vt 9` (and `--display-vt 9` to `run_ab_benchmark.py` / `run_cycle_benchmark.py` / `mechanism_evidence.py`) and verify `cat /sys/class/tty/tty0/active == tty9` before and after the run. When the console sits on an inactive VT (`tty2` while Xorg `:1` owns `vt9`), X11 frame presentation throttles to ~1 Hz: in `r179` (`Charts-chartjs`) and `r185` (13-story probe batch), running on `tty2` inflated story times by 15–100x (`11,648 ms` vs `50 ms`) and wasted two rounds. `measurement_host.display_environment` and `campaign.require_campaign_display` now fail closed if an X11 measurement runs on the wrong console VT.
