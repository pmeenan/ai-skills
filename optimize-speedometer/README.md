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

The orchestrator is explicitly accountable for the measured release-build
outcome. The landed-patch target is not a success criterion. Every evidence
boundary also gets independent read-only skeptic and adversary challenges,
aimed at finding ways an agent could satisfy the process without making Chrome
faster. These challenges can pause work but cannot override a failed machine
gate.

The current workflow has three deliberately separate evidence layers, each
scoped per story:

1. exact sync/async score-window profiles, decomposed into 32 independent
   story silos with shares local to each story's scored cycles, discover
   broad areas; opportunities rank globally by impact on their own target
   story (cross-story benefit is a bonus, never ranked);
2. instrumented calls/applicability/avoidable/exclusive-cycle blocks prove
   one mechanism on its target story only; the probe emits machine rows which
   `mechanism_evidence.py` digest-binds and reduces without transcription;
3. a fresh-seed randomized A/B over the ledger-preregistered target-story set
   gates landing efficacy, while a separate periodic full-suite A/B guards
   regressions and supports the aggregate score claim.

Profile share alone is never treated as predicted score movement. The
investigation ranking multiplies bound local-story share by a reviewed
avoidable fraction, while only measured counters and A/B checkpoints prove
effects. Manual ceilings,
unbound or placeholder review prose, typed test claims, comment-only diffs,
hand-authored counter JSON, and copied checkpoint numbers are rejected by the
ledger. Checkpoint v3 preserves every raw scalar Crossbench result, its digest,
arm position, and monotonic bounds; the ledger recomputes the paired statistic
instead of trusting either summary JSON. Build/test commands produce tree-bound receipts; capture manifests are
reduced from nonce-bound raw browser logs. Mechanism provenance invokes its
own bare-metal `autoninja` rebuild and binds the build/capture/receipt host,
boot, kernel, CPU, source trees, ELF and executable-`.text` identities, and
renderer PID/TID timestamps.
The default discovery floor is
0.3%, with a minimum of 100 nominal samples at that floor. The next landing is
blocked after five runtime changes without a fresh enabled profile, five
landings without a targeted checkpoint, or ten post-pilot landings without a
full-suite checkpoint.

The first five real candidates are a mandatory pilot. The sixth landing is
blocked until a targeted A/B over the exact landed target-story set shows a
positive 95% confidence interval and a separate same-tip full-suite A/B shows
no stat-sig regression. A positive point estimate whose interval crosses zero
leaves the pilot pending; use the MDE to preregister one larger confirmation
run. The ledger permits only that one larger targeted confirmation at the same
tip and rejects duplicate same-tip full-suite runs. A statistically negative
pilot fails permanently and requires repairing
or restarting the campaign rather than explaining the result away. After the
pilot, a flat current-tip targeted checkpoint or any statistically negative
full-suite checkpoint blocks further landings.

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
Every ledger save also creates a snapshot commit inside the campaign
directory. `campaign.py audit` reopens and deterministically recomputes all
retained evidence, receipts, reviews, checkpoint raw results, gate challenges,
skill digests, and snapshot state.
This is tamper-evidence, not a cryptographic trust boundary: an agent with
write access can also rewrite local Git history or tooling. The human trust
decision is the reviewed skills commit plus the reported campaign snapshot
head and a clean `campaign.py audit`; reviewer task/transcript references are
audit trails, not signatures.

## Prerequisites

- **Local machine**: Chromium checkout with the campaign branch (default
  `speedometer`) checked out and this skills repo present under
  `.agents/skills/`. Local build directories are not evidence prerequisites;
  authoritative builds and measurements run on the bare-metal host.
- **Remote measurement machine** (default ssh host `linux`): bare-metal box
  with PMU access, full Chromium checkout sharing upstream history, and two
  official non-debug PGO phase-2 ThinLTO builds. Use `out/perf` for profiling
  with symbols/frame pointers and `out/release` for authoritative score
  measurement without symbols. Both build identities are recorded as
  provenance. The host also needs `perf`, `vpython3`, `autoninja`, and `gn` on
  the PATH of a non-interactive ssh shell.
  `out/perf` is exclusively the official profile build with symbols;
  `out/release` is exclusively the authoritative symbol-free score build.
  The separate `out/perf_instrumented` mechanism twin, its provenance command,
  mechanism captures, and candidate build/test receipt commands also run on
  this bare-metal host; they are not local-workstation evidence.
  Budget disk generously: binary-vs-binary comparisons (`ab2` mode — used
  for bisects and candidate screens) maintain two additional official release
  dirs (`out/release_a`, `out/release_b`) beside those builds, so plan on the order
  of 200 GB free in the remote checkout.
- **Skills synced on both machines**: the skill scripts are gitignored in
  Chromium and are never transferred by the tooling. On each machine,
  `.agents/skills` must resolve into a standalone Git clone of this skills
  repository at the reviewed commit; an rsync/copy inside the Chromium tree
  is not trusted. Clone or update that skills repo on the remote host before a
  session — this is a **human** operation;
  agents are instructed to stop and ask rather than sync it themselves.
  Every remote job verifies a content digest and refuses to run (exit 5)
  on mismatch.
- **Committed skill tooling**: `campaign.py init` refuses copied, untracked,
  or dirty skill code. Have a human review and commit these enforcement scripts, then
  sync that exact commit to the remote host. The digest is stamped into the
  ledger, mechanism provenance/captures, command receipts, and score manifests.
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

The intended topology is explicit: profiles and cumulative checkpoints use
`remote_measure.py`, which transfers a committed SHA (or its `STAGED`
provisional commit) and builds it remotely. Mechanism provenance, instrumented
captures, and build/test receipts run directly in the configured bare-metal
campaign checkout against its fully staged review tree. Do not generate those
artifacts on a workstation and do not hand-transfer JSON in lieu of the tree.

The defaults (branch `speedometer`, target 20, flag
`Speedometer3Optimizations`, host `linux`) fit the usual environment, but
state the config, workflow, and autonomy level explicitly on the first run:

> Using the optimize-speedometer skill, start a Speedometer 3 optimization
> campaign driving for a cumulative score improvement on `out/release`.
> - **Campaign Configuration**: Campaign name `sp3-per-benchmark`, branch `speedometer`
>   (checked out), remote host `linux` (skills already synced there).
> - **Per-Story Workflow**: Explore each of the 32 benchmark stories as an
>   independent silo: per-story exact-scored profiles down to the 0.3% local
>   story floor, a global opportunity ranking by impact on each entry's own
>   target story (cross-story benefit is bonus, not ranked), and high-SNR
>   single-story sizing and candidate verification against the target story.
> - **Architectural Focus**: Reject Layer 4 ThinLTO/PGO micro-branch squeezes. Target
>   Layer 1 (Subtree / Lifecycle Phase Bypasses) and Layer 2 (Cross-Call State Memoization).
> - **Remote Transfers**: Always use compression flags (`scp -C` and `rsync -avz`) for all
>   remote transfers.
> - **Autonomy**: Drive the work autonomously as tech lead, using subagents for investigations
>   and independent reviews. Report with the STATUS.md summary after each milestone;
>   stop on any stopping rule or anything requiring human intervention.

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
ledger, runs `campaign.py audit`, regenerates status, verifies artifacts at the next gate, and resumes
without reconstructing evidence from prose.

A targeted 32-block checkpoint executes 128 repetitions of only the landed
target-story set; a full-suite checkpoint executes 128 complete Speedometer
repetitions and has a 64-minute hard plausibility floor. Long quiet periods are
expected. When a targeted interval crosses zero, use its MDE to select one
larger preregistered balanced confirmation run rather than rerunning seeds
until one looks favorable; the ledger enforces the one-confirmation limit.

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
Before accepting a checkpoint or final result, run:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py audit
```

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
| `scripts/mechanism_evidence.py` | Runs nonce-bound captures, validates raw browser logs, and computes paired mechanism statistics |
| `scripts/command_evidence.py` | Executes build/test commands and emits staged-tree-bound receipts |
| `resources/` | Flag/probe scaffolding, instrumented-twin, mechanism-evidence, decomposition, and analyzer references |
| `../chrome-cycle-profiling/` | Companion skill: capture mechanics, A/B statistics |
