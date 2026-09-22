<!-- Generated from ../../helper-cli.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

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

## Leases and the shared worktree

```
worktree-lease.py acquire        --review-dir DIR --holder KEY [--stale-seconds N] [--force] <lease-dir>
worktree-lease.py heartbeat      [--stale-seconds N] <review-dir> <message>
worktree-lease.py check          [--stale-seconds N] <review-dir>
worktree-lease.py holder-of      [--stale-seconds N] <review-dir>
worktree-lease.py holders        [--stale-seconds N] <lease-dir>
worktree-lease.py release        <review-dir> [message]
worktree-lease.py release-token  <lease-dir-or-log> <token> [message]
worktree-lease.py write-state    <review-dir> <lease-log> <token> <holder>
worktree-lease.py validate-state <review-dir>
worktree-lease.py gc             --repo REPO --worktree-root ROOT --exclude EXCLUDE [--stale-seconds N]
```

`<lease-dir>` is the **pin lock directory**, not a review directory:

```
<src-parent>/codereview/locks/cl-<CL>-ps<PS>/
```

with `<src-parent>` the parent of `CHROMIUM_SRC`. That directory holds one
append-only JSON-lines progress log per holder, `<holder>.log`.
`write-state` requires that **holder log file** as `<lease-log>`:
`<lease-dir>/<holder>.log`, using the holder passed to `acquire` and the token it returns. Passing the pin lock directory to `write-state` is invalid.
`release-token` accepts either the pin lock directory or the holder log file.

The review directory contains `pin.md` recording the initial pin and mutable
`lease-state.json` recording the authenticated current log path plus an
unguessable owner token. The mutable state is operational metadata and is
never a sealed worker input.

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
