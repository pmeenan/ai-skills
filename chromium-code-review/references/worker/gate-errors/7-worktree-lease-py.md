<!-- Generated from ../../gate-errors.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Gate-error lookup table

**Rule this file enforces: never read or grep a helper script's source to work
out what a gate rejection meant.** Look the message up here. If the message you
hit is missing, adding it to this file is part of the fix — the next run must
not have to re-read the script either.

**Do not read this file end to end — query it.** At over 700 rows it is a
database, and reading it would simply relocate the cost it exists to remove:

```sh
<skill-dir>/scripts/explain-gate-error.py "<the message you saw>"
```

Paste the message verbatim, including paths and line numbers; the lookup
ignores them and matches the parameterized form below. Exit 1 means no row
matched, and adding one is then part of the fix.

By hand, if you must: take the distinctive substring of the failure (usually
the part after `ERROR: ` or `<script>.py: ERROR: `), find it in the table for
the script that produced it, and apply the **Fix** verbatim. The trailing **Source** column
names the file and line so a maintainer can re-verify a row; you do not need to
open it to act on the row.

`validate-review-dir.py` prints every finding as `ERROR: <message>` or
`WARNING: <message>` and ends with `FAIL: <n> error(s), <m> warning(s)` or
`PASS: 0 errors, <m> warning(s)`. Warnings never fail the gate. Every other
script prints `<script-name>: ERROR: <message>` on stderr and exits 1.

---

## 7. `worktree-lease.py`

Subcommands: `acquire`, `write-state`, `validate-state`, `heartbeat`,
`release`, `release-token`, `check`, `holder-of`, `holders`, `gc`.
Default stale window is 3600s (`DEFAULT_STALE_SECONDS`, overridable with
`--stale-seconds` and `CHROMIUM_REVIEW_LEASE_SECONDS`).

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| **`lease is stale (<N>s since progress; limit 3600s): <path>`** | From `check`. The lease still exists and is still yours, but no `heartbeat` was recorded within the stale window. | Record progress at least once per window: `worktree-lease.py heartbeat <REVIEW_DIR> "<what you just finished>"`. Do this after every long phase, not only at the end. | worktree-lease.py:655 |
| **`lease expired <N>s after its last progress; reacquire before continuing`** | From `heartbeat`. The lease lapsed before you tried to record progress. | Re-acquire: `worktree-lease.py acquire <LEASE_DIR> --review-dir <REVIEW_DIR> --holder <KEY>`, then continue. Confirm the pin still matches before trusting earlier work. | worktree-lease.py:604 |
| **`this review's lease expired <N>s after its last progress (limit <L>s): <path>. It must stop rather than silently revive; pass an explicit --holder only if the user confirms restarting it.`** | The review lost its lease and another run may have taken the pin. | Stop. Report to the user. Only restart with an explicit `--holder` after the user confirms. | worktree-lease.py:727 |
| `this review's lease at <path> is now held by another review; it was replaced and must stop. ...` | Another review took the pin. | Stop and report. Do not take it back without user confirmation. | worktree-lease.py:737 |
| `this review's lease ended with '<reason>' (<detail>); it was replaced or expired and must stop rather than resume under a new identity.` | The lease log shows a terminal event. | Stop and report. | worktree-lease.py:757 |
| `no lease history for this review under <path>` | No lease log at all. | Acquire a lease before running lease-dependent commands. | worktree-lease.py:763 |
| **`timed out waiting for lease mutation guard: <path>`** | Another `worktree-lease.py` invocation held the flock. | Retry after the other invocation finishes. If a stale process is wedged, check with `worktree-lease.py holders <LEASE_DIR>` before intervening. Do not delete the lock file. | worktree-lease.py:108 |
| `holder <H> already holds this pin (<N>s since progress; review <R>): <path>. Concurrent reviews must pass a distinct --holder; use --force-restart only after explicit user confirmation.` | Two reviews used the same holder key on one pin. | Re-run with a distinct `--holder <KEY>` per concurrent review. Only use `--force-restart` after the user confirms. | worktree-lease.py:546 |
| `lease is absent; reacquire before continuing: <path>` | The lease directory is gone. | Run `worktree-lease.py acquire ...`. | worktree-lease.py:598 |
| `lease was replaced by another review: <path>` | Token mismatch during heartbeat. | Stop; another review owns the pin. | worktree-lease.py:601 |
| `active lease is absent: <path>` | `check` found no active lease. | Re-acquire. | worktree-lease.py:649 |
| `lease token does not match this review: <path>` | `lease-state.json` token disagrees with the active lease. | Re-acquire, then `worktree-lease.py write-state <REVIEW_DIR> <LEASE_DIR> <TOKEN> <HOLDER>`. | worktree-lease.py:652 |
| `lease is already absent: <path>` | `release` on a released lease. | Nothing; this is idempotent noise. | worktree-lease.py:615 |
| `refusing to release another review's lease: <path>` | Release attempted from the wrong review. | Release from the owning review directory only. | worktree-lease.py:618 |
| `active lease path still exists after release: <path>` | Release did not take effect (usually a read-only filesystem). | Move the review directory to local disk (see §8) and retry. | worktree-lease.py:622 |
| `release archive was not created: <path>` | Archive write failed. | Check write permissions on the lease directory. | worktree-lease.py:624 |
| `required authenticated lease state is absent: <path>` | No `lease-state.json`. | Run `worktree-lease.py write-state <REVIEW_DIR> <LEASE_DIR> <TOKEN> <HOLDER>`. | worktree-lease.py:367 |
| `cannot read authenticated lease state <path>: <err>` | Unreadable/corrupt JSON. | Delete `lease-state.json` and re-run `write-state`. | worktree-lease.py:372 |
| `<path> has an unsupported lease-state schema` | Old-format state file. | Delete it and re-run `write-state`. | worktree-lease.py:374 |
| `<path> <field> does not authenticate against this review/pin: <a> != <b>` | The state file belongs to a different review or pin. | Re-run `write-state` from the correct review directory. | worktree-lease.py:385 |
| `<path> has no valid holder` | Holder field missing. | Re-run `write-state` with the holder key. | worktree-lease.py:393 |
| `<path> has no absolute lease_log` | `lease_log` is relative. | Re-run `write-state`. | worktree-lease.py:396 |
| `<path> lease_log is not the authenticated holder/pin path` | `lease_log` points elsewhere. | Re-run `write-state`. | worktree-lease.py:406 |
| `<path> has no valid lease token` | Token missing. | Re-run `write-state` with the token printed by `acquire`. | worktree-lease.py:408 |
| `lease state token must be 32 lowercase hexadecimal characters` | Malformed token argument. | Pass the exact token from `acquire`; do not retype it. | worktree-lease.py:429 |
| `lease state path does not match the requested holder and pin` | Mismatched `write-state` arguments. | Pass the same `<LEASE_DIR>`, token, and holder that `acquire` used. | worktree-lease.py:439 |
| `cannot authenticate absent active lease: <path>` | No active lease to authenticate. | Re-acquire first. | worktree-lease.py:444 |
| `lease token does not own <path>` | Wrong token. | Use the token from the current `acquire`. | worktree-lease.py:447 |
| `lease <path> belongs to another review directory` | Cross-review token use. | Use the lease that belongs to this review. | worktree-lease.py:449 |
| `lease <path> records another holder` | Holder mismatch. | Use the holder key recorded at acquire time. | worktree-lease.py:451 |
| `review has no <file>; legacy pin fallback remains valid` | Expected state file absent; the caller falls back to `pin.md`. | Usually informational for the caller; run `write-state` to move to the authenticated path. | worktree-lease.py:494 |
| `review has no pin.md: <path>` | No pin. | Run `fetch-cl.sh <CL> <PS> <REVIEW_DIR>` first. | worktree-lease.py:681 |
| `<path> records no worktree lease` | `pin.md` has no lease lines. | Acquire a lease, then re-run `fetch-cl.sh` so `pin.md` records it. | worktree-lease.py:700 |
| `<path> has no mechanically readable pin identity` | `pin.md` CL/patchset/SHA lines are malformed. | Regenerate `pin.md` with `fetch-cl.sh`. | worktree-lease.py:344 |
| `--stale-seconds must be at least 60` | Value too small. | Pass ≥ 60. | worktree-lease.py:78 |
| `--holder must be 1-64 characters of [A-Za-z0-9_-] and start with an alphanumeric: <h>` | Bad holder key. | Use something like `review1` or `agent-a`. | worktree-lease.py:84 |
| `holder log is not inside a pin lock directory: <path>` | Lease layout is corrupt. | Re-acquire the lease from scratch. | worktree-lease.py:716 |
| `archived corrupt lease <a> as <b>` *(warning)* | A malformed lease file was moved aside automatically. | No action. | worktree-lease.py:192, :283 |
| `migrated single-holder lease <a> to ref-counted holder <b>` *(warning)* | Old-format lease upgraded in place. | No action. | worktree-lease.py:291 |
| `preserving non-empty unregistered cache directory <p>; inspect and remove it manually if safe` *(warning, `gc`)* | `gc` refused to delete an unknown directory. | Inspect it, then remove it yourself if it is junk. | worktree-lease.py:876 |
| `preserving dirty inactive worktree <p>; inspect it, then run git -C <repo> worktree remove --force <p> only if safe` *(warning, `gc`)* | `gc` refused to delete a dirty worktree. | Run the quoted `git worktree remove --force` only after confirming nothing is needed. | worktree-lease.py:890 |
| `preserving unreadable inactive worktree <p>` *(warning, `gc`)* | Permissions problem. | Inspect manually. | worktree-lease.py:888 |
| `could not prune archived lease <p>: <err>` *(warning)* | Cleanup failed. | Harmless; remove the archive manually if it accumulates. | worktree-lease.py:807 |
| `could not remove <p>: <err>` *(warning, `gc`)* | Cleanup failed. | Harmless; remove manually if needed. | worktree-lease.py:904 |

---
