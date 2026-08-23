# Optimize benchmark campaigns

This is the human-facing operations guide for the shared Chromium benchmark
optimization pipeline. Agents start with `SKILL.md`; campaign operators should
start here.

The shared core coordinates profiling, mechanism sizing, guarded
implementation, independent reviews, randomized score checkpoints, and a
tamper-evident campaign ledger. Thin benchmark skills supply benchmark
semantics and policy:

- `optimize-speedometer` supports the complete profile, mechanism, and score
  campaign loop.
- `optimize-jetstream` supports local integration characterization and
  immutable-payload score evidence. Exact-window profiling and mechanism
  sizing remain deliberately blocked until their trace path is verified.

The landed-patch target is a planning limit, not success. A successful campaign
requires a reproducible release-role aggregate result with a confidence
interval. Profile share finds work; mechanism counters prove work removal;
randomized score A/B proves benchmark movement. None substitutes for another.

## Prerequisites

### Chromium checkout

Start Codex in the Chromium `src` root with the intended campaign branch
checked out. `.agents/skills` must point to a standalone clone of this skills
repository. Campaign discovery and the default ledger path are based on the
current working directory.

For functional Chrome characterization, an existing `out/Default/chrome` and
matching `out/Default/chromedriver` are sufficient. Development builds never
produce authoritative campaign evidence.

### Authoritative builds

Authoritative score measurement uses the recorded release role, normally the
official non-debug PGO phase-2 ThinLTO `out/release` build. Speedometer exact
profiling uses the corresponding symbols/frame-pointer `out/perf` role.
Speedometer mechanism capture uses a separate release-like
`out/perf_instrumented` twin.

Binary-vs-binary comparisons may also create `out/release_a` and
`out/release_b`. On an SSH measurement checkout, budget roughly 200 GB free for
all build directories and artifacts.

### Physical measurement host

Both execution modes require physical hardware for authoritative evidence.
The host needs Chromium build prerequisites plus `perf`, `vpython3`,
`autoninja`, and `gn` available to the process running the campaign.

- `--execution local` uses the current checkout and never checks out or
  rewrites a ref. The requested committed ref must be current HEAD.
- `--execution ssh` transfers committed refs, checks them out detached on the
  measurement host, builds there, and runs under the shared host lock.

Local execution is appropriate when Codex is already running directly on the
physical measurement machine. It does not weaken build-role, payload,
virtualization, or evidence gates.

### Skills repository trust

`campaign.py init` requires clean, committed skill code. The reviewed skill
tree digest is recorded in the ledger and bound into profiles, mechanism
artifacts, command receipts, and score manifests.

For SSH execution, `.agents/skills` on the remote Chromium host must resolve to
the same reviewed skills commit. The runner checks the digest and stops rather
than copying or repairing skill code. Updating that clone is a human operation.

## Environment variables

Command-line arguments take precedence over these defaults:

| Variable | Purpose |
| --- | --- |
| `OPTIMIZE_CAMPAIGN_DIR` | Campaign directory; otherwise `.agents/campaigns/current` |
| `OPTIMIZE_CAMPAIGN_REMOTE_HOST` | SSH measurement host |
| `OPTIMIZE_CAMPAIGN_REMOTE_SRC` | Chromium `src` path on the SSH host |

The test-only bypass variable is not a user control and is ignored outside an
in-process unit test.

## Starting a campaign

The pipeline resumes `.agents/campaigns/current/ledger.json` when it exists.
To start over, archive the old campaign directory and deliberately replace the
`current` link. Do not ask the agent to overwrite an existing ledger.

### Speedometer

A useful first-session prompt is:

> Use the optimize-speedometer skill to start a Speedometer 3 optimization
> campaign on branch `speedometer`. Run measurements locally on this physical
> host, use the recorded Speedometer exact-story workflow, and drive through
> the pilot autonomously. Stop for any machine-gate failure or human decision,
> and report STATUS.md after each milestone.

For SSH execution, name the host and remote Chromium path and state that the
reviewed skills commit is already synchronized. If you want a bounded session,
add “run until the next checkpoint, then stop and report.”

Speedometer installs its exact `[SP3_SCORE_TIME]` probe once on the campaign
branch, runs A/A and empty-feature calibration, then enters the 3–5 candidate
pilot before scaling. The adapter reference owns the 32-story, repetition,
share-floor, and checkpoint policy.

### JetStream

Until exact profiling opens, start with a characterization request rather than
a full optimization campaign:

> Use the optimize-jetstream skill to characterize JetStream locally with the
> existing `out/Default/chrome` and matching chromedriver. Use a small custom
> workload run, preserve score components and payload provenance, and do not
> treat any numeric result as performance evidence.

Authoritative JetStream score work requires a pinned local payload tree. The
runner rejects symlinks, hashes the tree, serves it on ephemeral loopback, and
rehashes it after the run. `--custom`, live, or otherwise unpinned payloads
cannot be imported as checkpoints.

## Resuming

When `current` points to the intended campaign and the recorded branch is
checked out, this prompt is enough:

> Continue the benchmark optimization campaign using the selected benchmark
> skill. Audit the ledger and retained artifacts before resuming.

Preserve raw score results, profile/perf data, trace artifacts, counter logs,
capture manifests, build provenance, command receipts, review JSON, the
campaign Git directory, `ledger.json`, and `STATUS.md`. The agent runs:

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py status --print
python3 .agents/skills/optimize-campaign/scripts/campaign.py audit
```

The v4 ledger is intentionally clean-slate. Ledgers from older schemas are
rejected rather than migrated.

## Watching progress

`.agents/campaigns/<name>/STATUS.md` is regenerated on every ledger mutation.
It shows landed count, current gates, time in gate, the measured opportunity
order, latest profile, checkpoint history, and parked/rejected/reverted work.
`ledger.json` is the machine source of truth and must never be edited manually.

Long quiet periods are normal during official builds and benchmark blocks.
Speedometer's 32-block all-story checkpoint means 128 full repetitions and has
a 64-minute minimum-duration plausibility gate; it may take several hours.

## Shared lock and recovery

Local and SSH measurements serialize on:

```text
/tmp/chromium-benchmark-measure.lock
```

Exit code 75 means another process holds the lock. Normally wait or let the
agent retry. A persistent 75 can indicate a hung holder. Inspect it first:

```bash
fuser -v /tmp/chromium-benchmark-measure.lock
```

On a remote host:

```bash
ssh <host> 'fuser -v /tmp/chromium-benchmark-measure.lock'
```

Only after confirming that the holder is stale, terminate that process with
`fuser -k` locally or through SSH. Never delete the lock file: `flock` is held
on an open inode, so removing the pathname does not release the old lock and
can allow a second job to run concurrently on a new file.

## Other stop conditions

- **Exit 4 — measurement tree dirty:** tracked changes exist in the SSH
  checkout. Inspect and deliberately clean or stash them on that host.
- **Exit 5 — skills out of sync:** update the standalone skills clone on the
  measurement host to the reviewed commit, then retry.
- **Exit 75 — lock busy:** wait, or inspect a persistently hung holder as
  described above.
- **Exact profile or mechanism capability unavailable:** do not substitute
  whole-page timing or another benchmark's mechanism runner.
- **Regression surviving confirmation/bisection or correctness conflict:** the
  campaign stops for a human decision.
- **Dirty local source with `STAGED`:** fully stage the intended candidate or
  explicitly resolve unrelated files; do not let a provisional measurement
  silently exclude work.

Compress remote transfers with `scp -C` or `rsync -z`.

## Useful steering additions

- “Reprofile first and rebuild the opportunity list.”
- “Run until the next checkpoint, then stop and report.”
- “Prioritize renderer main-thread candidates.”
- “The reviewed skills commit is now synchronized remotely; retry.”
- “Characterize integration only; do not collect authoritative evidence.”

## Layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Shared capability routing and non-negotiable contracts |
| `references/campaign-runbook.md` | Agent campaign state-machine workflow |
| `references/playbooks/` | Bounded profiler, investigator, implementer, reviewer, and measurer roles |
| `scripts/campaign.py` | Ledger, gates, audit, and STATUS generation |
| `scripts/remote_measure.py` | Local/SSH execution, lock, ref, and digest enforcement |
| `scripts/benchmark_adapters.py` | Benchmark identity, parsing, direction, workload, and payload seam |
| `scripts/analyze_stacks.py` | Overlap-aware profile frontier analysis |
| `scripts/mechanism_evidence.py` | Runner-owned mechanism capture and paired reduction |
| `scripts/command_evidence.py` | Staged-tree-bound build and test receipts |
| `../optimize-speedometer/` | Speedometer trigger and calibrated policy |
| `../optimize-jetstream/` | JetStream trigger and payload/profile policy |
| `../chrome-cycle-profiling/` | On-host score and cycle runners |
