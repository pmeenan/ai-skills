# Chromium optimization campaigns

The shared pipeline discovers unnecessary renderer main-thread work, qualifies
concrete mechanisms against measured floors, and verifies improvements with
randomized, family-adjusted A/B measurement on one fixed rendering surface.
Start the agent with `SKILL.md`; read [measurement policy](references/measurement-policy.md)
for the evidence rules and landing requirements.

## Host prerequisites (operator, once per machine)

Run from the Chromium `src` directory with `.agents/skills` pointing to a
reviewed, committed clone of this repository. The measurement host needs:

- **A GPU-backed X display for benchmark runs.** Headless Chrome renders
  through SwiftShader, which puts canvas rasterization and CPU raster on the
  renderer main thread; the Mac M1 PGO fleet bots use GPU raster and
  accelerated canvas. On the Linux box a root-owned `xorg-benchmark.service`
  runs Xorg on `:1` at VT 9 with a fixed 1920x1080 virtual screen and no window
  manager, and `xhost` grants the benchmark user. Only the X server owning the
  active VT renders on the NVIDIA driver, so the tuner switches to VT 9 for a
  session and back afterwards; the desktop on VT 2 is untouched otherwise.
- **Passwordless sudo** for the tuner (`chvt`, sysfs CPU policy, optional
  `nvidia-smi --lock-gpu-clocks`).
- **No other GPU tenants during measurement sessions.** Name them at init
  (`--pause-service ollama`); the tuner stops those services for each session
  and restarts them afterwards, so occasional use between sessions is fine.
  A foreign compute process that appears mid-run still invalidates the run.
- Official PGO/ThinLTO builds: `out/release` (symbol-free score build) and
  `out/perf` (symbols and frame pointers for profiles).

Everything else (CPU clocks, SMT, ASLR policy, VT handoff, GPU clock lock)
is session-scoped and restored by `tune_benchmark_host.py`.

## Start a new campaign

> Use optimize-campaign and optimize-speedometer to start campaign
> `speedometer-september` in `~/src/chromium/src`. Use Speedometer 3.1 with
> Pinpoint's 20 default workloads and the exact scored sync/async intervals.
> Use branch `speedometer`, frozen baseline `<full commit>`, display `:1` on
> VT 9, pausing `ollama` during sessions, and the Mac M1 PGO Pinpoint bot for
> fleet validation. Check for an existing campaign or active measurement
> first. Run two separately timed A/A sessions
> and record them with `campaign.py calibrate`, capture two main-thread
> profiles, and work the highest-floor-clearing story areas through the next
> checkpoint. Register every attempt before launch; preserve failed and
> inconclusive work. Report evidence, unresolved questions and the campaign
> directory.

For a bounded discovery session before any host time is spent:

> Use optimize-campaign to investigate the retained main-thread profiles in
> `<campaign directory>`. Spend up to two hours on architectural hypotheses
> per story area, starting from the score-time composition and the top
> inclusive parents, not the leaves. For each hypothesis name the redundancy
> probe site that would measure its applicability. Do not run benchmarks or
> change the checkout. Rank by plausible story impact against each story's
> calibrated floor; record honest stop reasons where nothing qualifies.

## Resume a campaign part-way through

> Resume optimize-campaign in `~/src/chromium/src`, using the existing campaign
> `.agents/campaigns/speedometer-september`. Audit `ledger.json`, retained raw
> artifacts, review/build receipts and the recorded attempt history.
> Preserve its baseline, display policy, calibration epoch, workload set,
> skill digest, candidate IDs and all failed/cancelled attempts. Check whether
> a measurement is still running and follow it before scheduling anything
> else. Continue from the first unfinished valid gate through the next
> checkpoint; do not initialize a new campaign, create a shadow manifest or
> reinterpret old results under new defaults. Report the exact blocker if
> evidence or calibration is invalid or missing.

If `current` is ambiguous, supply the explicit directory to every command:

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py \
  --dir .agents/campaigns/speedometer-september status --print
python3 .agents/skills/optimize-campaign/scripts/campaign.py \
  --dir .agents/campaigns/speedometer-september audit
```

An in-progress campaign is bound to its old skill digest, display policy and
calibration epoch. Finish or stop the active measurement before adopting a
newly reviewed skill version; a display or host-policy change means a new
campaign with fresh calibration and fresh profiles.

## What to preserve

Retain the campaign Git history, `ledger.json`, `STATUS.md`, failed/cancelled
attempts, exact profiles and traces, counter logs, redundancy packets, raw
score outputs, manifests, Pinpoint summaries, build/test receipts and review
reports. Status markdown is an export; the ledger is the authority. Save new contextual rejection lessons
in the campaign and update reusable skill references between campaigns.

An IMPROVEMENT requires a fixed primary effect and simultaneous regression
bounds. INVALID, INCONCLUSIVE and REGRESSION do not pass. A positive local
number is not proof of an optimization that will ship; the Mac M1 PGO bot is
the validation reference, and locally flagged rendering-backend work needs
that confirmation before more host time is spent on it.
