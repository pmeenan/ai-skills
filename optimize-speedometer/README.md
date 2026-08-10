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

The current workflow has three deliberately separate evidence layers:

1. exact sync/async score-window profiles, normalized to equal suite weight,
   discover broad areas;
2. instrumented calls/applicability/avoidable/exclusive-cycle blocks prove one
   mechanism; the probe emits machine rows which `mechanism_evidence.py`
   digest-binds and reduces without transcription;
3. fresh-seed randomized block A/B measures the aggregate score.

Profile share is never converted to predicted score impact. Manual ceilings,
unbound review prose, and copied checkpoint numbers are rejected by the
ledger. The default discovery floor is 0.3%, with a minimum of 100 nominal
samples at that floor. The next landing is blocked after five runtime changes
without a fresh enabled profile or five landings without a checkpoint.

The ledger deliberately separates a profiled **candidate area** from a
specific **optimization mechanism**. An area investigation fans out into
independently gated child mechanisms. Rejected/reverted mechanism keys remain
ruled out across follow-on profiles, while residual hot work in the same area
can produce new mechanisms. A landing never marks its parent area exhausted;
a fresh flag-enabled profile is required.

Each follow-on profile is imported atomically from a complete reconciliation
manifest: discoverable areas become discovery records, while excluded
payload/idle/out-of-scope rows retain structured evidence. Every raw machine
frontier entry from two independently identified, quality-passing captures is
accounted exactly once, with recurrence judged on symbol-level semantic work
identity so capture-fragile context keys and context/function drift cannot be
dropped. The mechanical
halves of both big JSON handoffs are generated, not hand-written:
`campaign.py profile-scaffold` prefills the reconciliation manifest and
`campaign.py decompose-scaffold` prefills a decomposition's per-hotspot
accounting. `mechanism_evidence.py scaffold/ingest/summarize/compare` performs the
candidate arithmetic, and `campaign.py review-scaffold` binds review checks
to the staged tree and evidence digests. Closing an area requires
a skeptic review of the decomposition's mandatory/out-of-scope/covered-by
claims before `exhaust` is accepted; a FAIL requires a revised decomposition
and cannot be overwritten on unchanged accounting. `campaign.py
audit-exhaustion` refuses
completion if any latest-profile area, active or relevant parked mechanism,
post-profile landing/revert, or checkout/branch mismatch remains unresolved.

## Prerequisites

- **Local machine**: Chromium checkout with `out/Default` configured; the
  campaign branch (default `speedometer`) checked out; this skills repo
  present under `.agents/skills/`.
- **Remote measurement machine** (default ssh host `linux`): bare-metal box
  with PMU access, full Chromium checkout sharing upstream history, and two
  official non-debug PGO phase-2 ThinLTO builds. Use `out/perf` for profiling
  with symbols/frame pointers and `out/release` for authoritative score
  measurement without symbols. Both build identities are recorded as
  provenance. The host also needs `perf`, `vpython3`, `autoninja`, and `gn` on
  the PATH of a non-interactive ssh shell.
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

The skill intentionally resumes `.agents/campaigns/current/ledger.json` when
it exists. To start from scratch, first archive or deliberately remove the old
campaign directory and its `current` link; do not ask the agent to overwrite
an existing ledger. This destructive choice remains a human operation.

A clean-slate campaign installs the exact `[SP3_SCORE_TIME]` probe from this
skill in place of the old outer-window `[SP3_MONO_TIME]` probe, compiles it,
and smoke-tests exact interval matching before its first profile. It then runs
a 3–5 candidate pilot through counters, oracle, candidate, and cumulative A/B
before scaling to a 20–40-change campaign.

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
> - Complete the 3–5 candidate counter → oracle → candidate → cumulative A/B
>   pilot, and continue to the long campaign only if the directions agree.
> - Then run the campaign loop. Report to me with the STATUS.md summary
>   after each checkpoint; otherwise proceed autonomously. Stop on any
>   stopping rule or anything needing human intervention.

The autonomy line is the one never to omit: everything else has a safe
default the agent will confirm, but "how far do you go before checking in"
is a preference it can only guess at.

## Resuming (every later session)

> Continue the Speedometer optimization campaign using the
> optimize-speedometer skill.

That is sufficient when `current` selects the intended campaign, the recorded
branch is checked out, the updated skills are synced locally and remotely,
and every digest-bound artifact still exists. Preserve raw counter logs,
profile and trace artifacts, A/A summaries, build-provenance files, derived
evidence JSON, the ledger, campaign commits, and STATUS.md. The agent reads the
ledger, regenerates status, verifies artifacts at the next gate, and resumes
without reconstructing evidence from prose.

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
next discovery/mechanism candidates in global measured-impact order (a hot
deep child raises its undecomposed parent and later competes directly), the latest overlap-safe
profile frontier, the checkpoint history (the diminishing-returns curve), and
parked/rejected/reverted/exhausted records with reasons.
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
- **Regression that survives bisect or a blocking correctness constraint** —
  decision points the campaign design reserves for you. The target count and
  flat checkpoints are reporting/re-profiling milestones, not automatic
  evidence that candidate areas are exhausted.

## Layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Tech-lead runbook: campaign loop, gates, stopping rules |
| `playbooks/` | Role playbooks: profiler, investigator, implementer, skeptic, adversary, measurer |
| `scripts/campaign.py` | Ledger, gate enforcement, STATUS.md generation |
| `scripts/remote_measure.py` | Remote measurement wrapper (ssh + lock + digest check) |
| `scripts/analyze_stacks.py` | Overlap-aware candidate frontier from perf stacks |
| `scripts/mechanism_evidence.py` | Raw counter validation and paired mechanism statistics |
| `resources/` | Flag/probe scaffolding, instrumented-twin, mechanism-evidence, decomposition, and analyzer references |
| `../chrome-cycle-profiling/` | Companion skill: capture mechanics, A/B statistics |
