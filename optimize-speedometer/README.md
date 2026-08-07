# optimize-speedometer

Human-facing guide for running a Speedometer 3 optimization campaign with
this skill. The agent-facing runbook is [SKILL.md](SKILL.md) — the agent
reads that; you read this.

The skill drives a long-horizon campaign: an agent acting as tech lead
coordinates subagents to profile Chromium on a remote bare-metal machine,
build a prioritized punch list from the profile, and incrementally land many
small optimizations (each expected to be under the score's noise floor) on a
dedicated branch behind one feature flag, with independent skeptic and
adversary reviews gating every landing. Score impact is measured in
aggregate at flag on/off checkpoints.

## Prerequisites

- **Local machine**: Chromium checkout with `out/Default` configured; the
  campaign branch (default `speedometer`) checked out; this skills repo
  present under `.agents/skills/`.
- **Remote measurement machine** (default ssh host `linux`): bare-metal box
  with PMU access, full Chromium checkout sharing upstream history,
  configured `out/perf` (PGO/LTO, frame pointers, symbols), and `perf`,
  `vpython3`, `autoninja`, `gn` on the PATH of a non-interactive ssh shell.
  Budget disk generously: binary-vs-binary comparisons (`ab2` mode — used
  for bisects and candidate screens) maintain two additional official build
  dirs (`out/perf_a`, `out/perf_b`) beside `out/perf`, so plan on the order
  of 200 GB free in the remote checkout.
- **Skills synced on both machines**: the skill scripts are gitignored in
  Chromium and are never transferred by the tooling. Sync this skills repo
  to the remote host before a session — this is a **human** operation;
  agents are instructed to stop and ask rather than sync it themselves.
  Every remote job verifies a content digest and refuses to run (exit 5)
  on mismatch.
- **Start the agent in the Chromium `src` root** — repo and campaign-ledger
  discovery are cwd-based.

## Starting a campaign (first session)

The defaults (branch `speedometer`, target 20, flag
`Speedometer3Optimizations`, host `linux`) fit the usual environment, but
state the config and the autonomy level explicitly on the first run:

> Using the optimize-speedometer skill, start a Speedometer 3 optimization
> campaign.
> - Campaign name `sp3-2026-08`, branch `speedometer` (checked out), target
>   20 landed optimizations, remote host `linux` (skills already synced
>   there).
> - Do the full setup: init the ledger, land the flag and probe scaffolding,
>   run A/A calibration and the flag-overhead null check.
> - Then run the campaign loop. Report to me with the STATUS.md summary
>   after each checkpoint; otherwise proceed autonomously. Stop on any
>   stopping rule or anything needing human intervention.

The autonomy line is the one never to omit: everything else has a safe
default the agent will confirm, but "how far do you go before checking in"
is a preference it can only guess at.

## Resuming (every later session)

> Continue the Speedometer optimization campaign using the
> optimize-speedometer skill.

That is sufficient. All campaign state lives in the ledger, the commit
messages on the campaign branch, and STATUS.md; the agent reconstructs
where it left off and picks up mid-loop without re-asking for configuration.

## Situational extras

Add to either prompt when relevant:

- "Re-profile first and rebuild the punch list before picking the next
  opportunity." — force a frontier refresh.
- "Run until the next checkpoint, then stop and report." — bounded session.
- "Prioritize renderer main-thread candidates." — scope steer.
- "Skills are re-synced on the remote; retry the measurement." — after a
  session stopped with exit 5.
- "Collect a fresh baseline profile with the flag disabled." — for
  before/after comparisons.

## Watching progress

`.agents/campaigns/<name>/STATUS.md` is regenerated on every ledger change:
landed count vs target, last checkpoint delta with confidence interval,
what is at each gate right now (with time-in-gate as a stall detector), the
next candidates in priority order, the checkpoint history (the
diminishing-returns curve), and parked/rejected opportunities with reasons.
`ledger.json` next to it is the machine-readable source of truth;
`dossiers/` and `reviews/` hold the per-opportunity artifacts.

## When the agent stops and asks for help

- **Remote lock busy (exit 75)** — another measurement is running; it
  retries or waits. The lock releases automatically when its holder exits,
  so a *persistent* 75 means a hung job, not a stale file. To recover, kill
  the processes holding the lock open:

  ```bash
  ssh linux "fuser -v /tmp/sp3-measure.lock; fuser -k /tmp/sp3-measure.lock"
  ```

  Never `rm` the lock file: flock is held on the open file descriptor, so
  deleting it doesn't release anything — it lets the next invocation lock a
  fresh inode and run concurrently with the hung job.
- **Remote tree dirty (exit 4)** — tracked modifications on the remote
  checkout; clean or stash them there.
- **Skills out of sync (exit 5)** — re-sync this skills repo on the remote
  host, then tell the agent to retry.
- **Regression that survives bisect, target reached, or a stopping rule** —
  decision points the campaign design reserves for you.

## Layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Tech-lead runbook: campaign loop, gates, stopping rules |
| `playbooks/` | Role playbooks: profiler, investigator, implementer, skeptic, adversary, measurer |
| `scripts/campaign.py` | Ledger, gate enforcement, STATUS.md generation |
| `scripts/remote_measure.py` | Remote measurement wrapper (ssh + lock + digest check) |
| `scripts/analyze_stacks.py` | Overlap-aware candidate frontier from perf stacks |
| `resources/` | Flag/probe scaffolding, analyzer reference |
| `../chrome-cycle-profiling/` | Companion skill: capture mechanics, A/B statistics |
