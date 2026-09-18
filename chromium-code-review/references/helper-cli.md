# Helper CLI Reference

**Never read or grep a helper script's source to work out how to call it.**
Look it up here. If an invocation you need is missing, adding it here is part
of doing the work.

For what an *error message* means, do not read
[gate-errors.md](gate-errors.md) either — it is a 700-row lookup table. Query
it instead:

```sh
<skill-dir>/scripts/explain-gate-error.py "<the message you saw>"
```

Paste the message verbatim; concrete paths, line numbers, and quoted values
are ignored when matching. `--max N` widens the result set. Exit 1 means no
row matched, and the corrective action is to add one once you know the fix.

> Measured over 31 runs of this skill, orchestrators opened helper source 725
> times — `validate-review-dir.py` alone 149 times across 8 conversations —
> and ran roughly 91 `--help` probes, purely to recover facts that are on this
> page.

Throughout, `<skill-dir>` means the sealed snapshot at
`<review-dir>/skill-snapshot`, not the canonical checkout, from the moment
`snapshot-skill.py` has run.

## Enumerations

Every value below was read from the scripts' own argparse definitions. A value
not in these tables is rejected outright.

| Enum | Legal values |
| --- | --- |
| `validate-review-dir.py --phase` | `auto`, `pin`, `collection`, `verification`, `reconciliation`, `final` |
| `validate-worker-artifact.py --kind` | `auto`, `inventory`, `plan`, `ledger`, `verdict`, `affinity`, `generic` |
| `seal-work-unit.py --tier` | `frontier`, `inherit`, `mechanical`, `standard` |
| subagent `Model` (check harness; Jetski default / Opus fallback) | `frontier` $\rightarrow$ `inherit` (`pro`/`opus`), `standard` $\rightarrow$ `flash` (`sonnet`), `mechanical` $\rightarrow$ `flash_lite` (`haiku`) |
| `seal-work-unit.py --input ROLE=` | `control`, `reference`, `assigned`, `candidate-packet`, `card`, `frame`, `section`, `prestate` |
| orchestration `state` | `queued`, `running`, `partial`, `retryable`, `needs-repair`, `complete`, `terminated` |
| `worktree-lease.py` subcommands | `acquire`, `write-state`, `validate-state`, `heartbeat`, `release`, `release-token`, `check`, `holder-of`, `holders`, `gc` |
| `log-progress.py` events | `spawned`, `collected`, `phase`, `note` |

There is no `list`, `status`, or `progress` lease subcommand; peers are
enumerated with `holders`, this review's own holder with `holder-of`.
There is no `inventory`, `planning`, or `discovery` validator phase; discovery
work validates under `collection`.

## Table schemas

`orchestration.tsv`, in order:

```
phase  work_id  attempt  state  tier  task_id  brief  artifact  remaining_scope  depends_on
```

`input-manifest.tsv`, in order:

```
work_id  attempt  phase  brief  input_path  role  bytes  sha256
```

**Neither file is ever edited by hand.** `orchestration.tsv` is written only by
`seal-work-unit.py`, `set-work-state.py`, and `await-workers.py`;
`input-manifest.tsv` only by `seal-work-unit.py` and `refresh-manifest.py`. All
of them take the same `fcntl.flock` guard on `<review-dir>/.orchestration.lock`
(timeout `CHROMIUM_REVIEW_GUARD_SECONDS`, default 30) and journal through
`.work-unit-seal-transaction.json`, so an interrupted mutation is healed by the
next one rather than leaving a torn file.

## Waiting for workers

```
await-workers.py [-h] [--work WORK_ID[:ATTEMPT]] [--timeout-seconds N]
                 [--poll-seconds N] [--heartbeat TEXT] [--no-heartbeat]
                 [--validate | --no-validate] [--no-transition] [--quiet]
                 review_dir
```

One blocking call that returns when the wave is done. Defaults: timeout 5400 s,
poll 30 s (both accept floats), validation on, state transitions on. `--work`
is repeatable; a bare `WORK_ID` selects its highest sealed attempt. With no
`--work`, the wave is every row in state `running` or `queued`.

While it waits it heartbeats the lease, stats each unit's `artifact`, runs
`validate-worker-artifact.py` at most once per `(path, mtime, size)`,
transitions satisfied units to `complete`, and appends the `collected` event to
`progress.md`. A heartbeat failure is reported in the summary and never aborts
the wait. It prints one line per unit, never artifact contents.

| Exit | Meaning | Do next |
| --- | --- | --- |
| 0 | every unit satisfied | proceed to the next phase |
| 2 | timeout, units still outstanding | inspect the named units; respawn or mark `retryable` |
| 3 | all finished, at least one `needs-repair` | repair or respawn the named units |

An empty wave prints `await-workers.py: nothing outstanding` and exits 0.

`CHROMIUM_REVIEW_ARTIFACT_VALIDATOR` overrides the validator command (shlex
split, invoked as `<cmd> <review-dir> <artifact>`); it exists for tests.

## Mutating work-unit state

```
set-work-state.py [-h] [--task-id TASK_ID] [--remaining-scope REMAINING_SCOPE]
                  [--note NOTE] [--log] [--force]
                  review_dir work_id attempt
                  {queued,running,partial,retryable,needs-repair,complete,terminated}
```

Changes the `state` of exactly one row — plus `task_id` / `remaining_scope` if
asked — and leaves every other byte of the file alone. Setting a row to the
state it already holds succeeds and prints `already <state>`. Transitions out
of `complete` or `terminated` require `--force`. `--log` also appends the
matching `progress.md` event (`complete` → `collected`, `running` → `spawned`,
otherwise `note`) and heartbeats the lease.

## Restamping prestate rows

```
refresh-manifest.py [-h] [--role ROLE] [--dry-run] review_dir work_id attempt
```

Recomputes `bytes` and `sha256` for that attempt's manifest rows. `--role` is
repeatable and defaults to `prestate`. Restampable roles: `assigned`,
`candidate-packet`, `card`, `control`, `frame`, `prestate`, `section`.
`brief` and `reference` are refused unconditionally — they are sealed
integrity anchors, and rehashing one would defeat the seal; reseal the attempt
instead. `--dry-run` reports the old→new deltas and changes nothing.

Use this instead of a hand-written `hashlib` snippet whenever a prestate input
grows between attempts and the gate reports a byte-count mismatch.

## Sealing a work unit

```
seal-work-unit.py [-h] --phase PHASE --work-id WORK_ID --attempt ATTEMPT
                  --tier {frontier,inherit,mechanical,standard}
                  --brief BRIEF --artifact ARTIFACT
                  [--depends-on DEPENDS_ON] [--remaining-scope REMAINING_SCOPE]
                  [--input INPUT]
                  review_dir
```

`--input` is repeated, once per input, as `ROLE=/absolute/path`. Seal before
spawning: sealing is what makes the brief read-only and records the attempt's
input bytes and hashes. `build-phase-brief.py` prints the exact command for
the brief it just generated — use that rather than assembling `--input` by
hand, because a guessed list is the usual cause of
`names input X but input-manifest.tsv omits it`.

## Generating a phase brief

```
build-phase-brief.py [-h] [--attempt ATTEMPT] [--shard SHARD] [--thread THREAD]
                     [--output OUTPUT] [--pathspec PATHSPEC] [--set KEY=VALUE]
                     [--allow-placeholders] [--phase PHASE]
                     [--tier {frontier,inherit,mechanical,standard}]
                     [--artifact ARTIFACT]
                     [--emit-seal-command | --no-emit-seal-command]
                     review_dir work_id brief_name
```

`brief_name` is the `## ` heading in `references/phase-briefs.md`; an unknown
name lists every available heading, so there is no reason to open that 81 KB
file to find one.

**It refuses to write a brief that still contains a `⟨...⟩` placeholder**,
listing each one with the flag that fills it. `--pathspec` fills the path-list
placeholders; `--set KEY=VALUE` fills `⟨KEY⟩` and is repeatable;
`--allow-placeholders` is the deliberate escape hatch. Placeholders the common
header leaves for the *worker* to resolve at runtime are allowlisted and do not
trip the check.

> This check is the fix for the most expensive recurring failure in the audit:
> a placeholder was hand-substituted out of a brief *after* the work unit was
> sealed, which changed the brief's bytes and produced
> `input-manifest.tsv: byte count mismatch` repair loops.

Unless `--no-emit-seal-command`, it then prints the exact `seal-work-unit.py`
command for what it wrote, with one `--input ROLE=path` for every absolute path
the gate will extract from the brief, `--phase` from the `(Phase N)` heading,
`--tier` from the `Tier:` line, and `--artifact` from the `Deliverable:` line.
**Run that command rather than assembling one**: a guessed `--input` list is
what produces `names input X but input-manifest.tsv omits it`. If a field
cannot be derived it prints a NOTE saying which flag to supply instead of a
command.

## Effort profiling

```
profile-review.py [-h] [--stdout] [--check]
                  [--tier-context-window-tokens TIER:TOKENS]
                  [--context-window-tokens N]
                  review_dir
```

Effort classes, cheapest first: `micro` (documentation and non-executable
metadata only), `trivial-code`, `standard`, and the heavier classes above it.
`trivial-code` requires all of: at most 4 changed files, 20 changed lines, 6
diff hunks, 6 approximate changed surfaces; at least one changed file; no
behavior-sensitive risk tokens in changed lines; no trigger-only specialist
lenses; no unresolved Gerrit threads; no supplied prior-review input; no
malformed normalized-comment entries. A failure is reported as
`trivial-code proof failed: <reason>`, and per-class results appear under
`micro_eligibility` and `trivial_code_eligibility`.

`micro` and `trivial-code` set `context_fast_path_eligible` and a collapsed
`topology` (`collapsed: true`, `initial_generalists: 1`,
`max_challenge_rounds: 1`). Act on those fields; do not re-derive them.

## Gates

```
validate-review-dir.py [-h]
                       [--phase {auto,pin,collection,verification,reconciliation,final}]
                       [--require-active-lease]
                       [--lease-stale-seconds LEASE_STALE_SECONDS]
                       review_dir

validate-worker-artifact.py [-h]
                            [--kind {auto,inventory,plan,ledger,verdict,affinity,generic}]
                            review_dir artifact
```

Pass `--require-active-lease` at every live phase gate; omit it for audit and
post-mortem validation after release.

## Leases and the shared worktree

```
worktree-lease.py acquire        --review-dir DIR --holder KEY [--stale-seconds N] [--force] <lease>
worktree-lease.py heartbeat      [--stale-seconds N] <review-dir> <message>
worktree-lease.py check          [--stale-seconds N] <review-dir>
worktree-lease.py holder-of      [--stale-seconds N] <review-dir>
worktree-lease.py holders        [--stale-seconds N] <lease>
worktree-lease.py release        <review-dir> [message]
worktree-lease.py release-token  <lease> <token> [message]
worktree-lease.py write-state    <review-dir> <lease> <token> <holder>
worktree-lease.py validate-state <review-dir>
worktree-lease.py gc             --repo REPO --worktree-root ROOT --exclude EXCLUDE [--stale-seconds N]
```

`<lease>` is the **pin lock directory**, not a review directory:

```
<src-parent>/codereview/locks/cl-<CL>-ps<PS>/
```

with `<src-parent>` the parent of `CHROMIUM_SRC`. That directory holds one
append-only JSON-lines progress log per holder, `<holder>.log`, `pin.md`
recording the initial pin, and mutable `lease-state.json` recording the
authenticated current log path plus an unguessable owner token. The mutable
state is operational metadata and is never a sealed worker input.

Staleness defaults to `CHROMIUM_REVIEW_LEASE_SECONDS` or 10800 s (three
hours), chosen to exceed observed worker latency — mean 49 minutes, maximum 79
— so that a lease does not expire mid-discovery. The floor is 60 s.

**Holder identity.** `--holder <key>` names the identity explicitly; the
default is stable across re-pins of one review directory, recovering the holder
that the authenticated lease state (or a legacy `pin.md`) already owns rather
than minting a second one. Derive it from the conversation id.

**Concurrency.** Materialization — ref fetch plus `git worktree add` — runs
under an exclusive per-pin lock, so the first holder pays for it and the rest
wait and reuse. Acquisition fails only when the *same* holder key already has a
live lease from a different review directory. A holder's lease older than the
staleness window is archived and replaced automatically. `--force-restart`
(on `fetch-cl.sh`) replaces only this holder's own fresh lease, requires
explicit user confirmation, and never evicts a peer; the replaced review's next
heartbeat fails by token mismatch and it must stop. Corrupt or empty holder
leases are archived and replaced rather than blocking the cache globally, and
archived logs older than 30 days are pruned.

**Worktree reclamation.** The worktree stays cached after release. A pin with
any live holder is never reclaimed. A later invocation removes fully released
or expired *clean* entries with `git worktree remove`; dirty or unreadable
entries are preserved and warned about, never force-removed. An expired lease
may be taken over after one hour, but its worktree is retained for a two-hour
grace so a delayed worker is not disrupted.

## Pin and snapshot

```
fetch-cl.sh <CL> [patchset] [review-dir] [--holder KEY] [--force-restart]
snapshot-skill.py [-h] [--check] skill_dir review_dir
```

`fetch-cl.sh` probes the review directory for `chmod` support before doing any
network or git work, because an x20/FUSE review directory cannot hold the
authenticated lease state and the failure would otherwise arrive only after the
expensive fetch. Keep the review directory on local disk:
`/tmp/cl-<CL>-ps<PS>-<holder>`.

On the first pin it writes `pin.md`, `detail.json`, `comments.json`, and
`lease-state.json`; a resume on the same CL/patchset/revision verifies them and
rewrites only the lease state.

`snapshot-skill.py` writes the immutable snapshot at
`<review-dir>/skill-snapshot` and verifies its manifest before reuse; `--check`
verifies without writing.

## Progress and cost

```
log-progress.py  <review-dir> spawned   <WORK_ID> <attempt> [text]
log-progress.py  <review-dir> collected <WORK_ID> <attempt> <text>
log-progress.py  <review-dir> phase     <label> <text>
log-progress.py  <review-dir> note      <text>

report-review-costs.py <review-dir>
archive-review-instrumentation.py [--canonical-skill-dir DIR] [--version V] <review-dir>
instrument-command.py [--cwd CWD] <review-dir> <work_id> <attempt> -- <command> [args...]
```

The cost report derives all wall-clock evidence from `progress.md`, so
spawn/collect/phase events must go through `log-progress.py`, which stamps UTC
itself and validates the shape. Work IDs are opaque whitespace-free tokens.

## Materialization and indexes

```
build-review-indexes.py [--output-dir DIR] [--check] <review-dir>
build-caller-index.py --worktree W --revision R [--pathspec P] <review-dir>
build-scope-packets.py --worktree W --parent P --revision R [--spec SPEC] [--output OUT] <review-dir> <work_id>
build-discovery-brief.py --work-id ID [--attempt N] --entry E --procedure P [--pathspec SPEC] [--output OUT] <review-dir>
```

Run `build-scope-packets.py` before sealing, so the scoped code packet is an
existing hashable `assigned` input rather than something every worker
re-derives from the worktree.

## Mechanical collection

```
extract-unresolved-comments.py [-o OUTPUT] <comments.json>
collect-challenge-round.py <review-dir> <round>
refresh-delivery-gate.py [--detail-json J] [--gerrit-base B] [--gerrit-project P]
                         [--checked-at T] [--accept-proven-trivial-delta] <review-dir>
```

These are deterministic. **Run them directly; never spend an agent executing
them.** `collect-challenge-round.py` exits nonzero when a round is structurally
incomplete — that is a repair signal, not a judgment about the review.
