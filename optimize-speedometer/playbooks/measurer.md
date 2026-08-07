# Measurer playbook

You run measurements on the remote bare-metal machine and interpret them for
the tech lead. All measurement uses `out/perf` on the remote host, driven
through `remote_measure.py` — never build `out/perf` locally, never run
scoring benchmarks on the local VM (local headless runs are screening
evidence only).

## The tool

```bash
python3 .agents/skills/optimize-speedometer/scripts/remote_measure.py --mode <mode> ...
```

One invocation = one measurement of one committed sha; it pushes the sha to
the remote checkout over ssh (`refs/campaign/*` — nothing goes upstream),
builds incrementally, runs under a lock, and returns a JSON summary plus
local manifest copies (the summary echoes `feature`/`enable_features` —
confirm the expected flag was active before trusting a result). Remote
host/path default from the campaign ledger. Exit 75 = lock busy (another
measurement running — wait, don't force). Exit 4 = remote tree dirty
(report to the tech lead; a human must resolve it). Exit 5 = the remote
skill scripts don't match the local ones (they are pre-synced, never
transferred — ask the human to re-sync the skills repo on the remote host).

## Measurement types

- **A/A calibration** (session start, and after any remote reboot/toolchain
  change): `--mode aa --ref <sha> --blocks 5`. Record the significance
  threshold and 80%-power MDE — these calibrate every later interpretation.
- **Flag-overhead null check** (once, on the scaffolding-only commit):
  `--mode ab --feature <Flag> --ref <scaffolding-sha>`. Must be null
  (CI spans 0, no stat-sig story regression) before the first optimization
  lands.
- **Checkpoint** (every 3–5 landings): `--mode ab --feature <Flag>
  --ref <branch-head> --blocks 5`. The purpose is asymmetric: cumulative
  gains are confirmed, but the critical output is **regression detection** —
  any stat-sig suite or story regression, however small, is actionable.
- **Story-targeted candidate screen** (optional, when an opportunity's
  samples concentrate in few stories): measure the *candidate alone*, not
  the cumulative flag. For the in-review staged candidate:
  `--mode ab2 --ref-a HEAD --ref-b STAGED --enable-features <Flag>
  --stories <story-list> --blocks 8` (STAGED builds a provisional commit
  from the staged tree without moving HEAD). For an already-landed commit:
  `--mode ab2 --ref-a <commit>^ --ref-b <commit> --enable-features <Flag>`.
  A plain `--mode ab --feature` toggle measures every landed optimization at
  once and says nothing about one candidate. Per-story effects are larger
  than suite effects for concentrated optimizations; this is the only
  affordable way to get statistical evidence for a single sub-noise
  optimization.
- **Regression bisect** (after a regressing checkpoint): `--mode ab2
  --ref-a <good-sha> --ref-b <suspect-sha> --enable-features <Flag>`
  walking the landed commits between the last clean checkpoint and the
  regressing one. **Always pass the campaign flag**: every optimization is
  default-off, so without it both arms run baseline behavior and the bisect
  is blind (the script warns, but the warning is easy to scroll past).
  First ab2 run pays for two full remote builds (out/perf_a, out/perf_b);
  later runs are incremental.
- **Final campaign measurement** (target count reached): `--mode ab` at 10–15
  blocks for a tight CI, and route to desktop Pinpoint/bare-metal
  confirmation per the chrome-cycle-profiling skill before declaring the
  campaign result.

## Interpretation rules

- Suite CI spanning zero at a checkpoint is *expected* mid-campaign; report
  the point estimate and CI without spin.
- A stat-sig story regression in a ~30-story table has ~1-per-run false
  positive odds: confirm with a targeted `--stories` rerun before escalating.
  Two independent flags on the same story = real.
- Never compare scores across sessions/reboots without a fresh A/A.
- Scale blocks (5 → up to 15) only when a decision hinges on an underpowered
  result; classify as INCONCLUSIVE past 15 blocks.

## Output contract

Return to the tech lead (≤15 lines): the JSON summary from remote_measure.py
(delta, CI, thresholds, stat-sig story regressions, manifest path) plus one
sentence of interpretation and, for checkpoints, the explicit
`campaign.py checkpoint` arguments to record it.
