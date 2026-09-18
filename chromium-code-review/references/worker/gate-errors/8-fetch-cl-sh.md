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

## 8. `fetch-cl.sh`

All messages print as `fetch-cl.sh: ERROR: <message>` (via `die`) and exit 1.

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| **`could not persist authenticated mutable lease state`** | `worktree-lease.py write-state` failed, almost always because the review directory is on a filesystem where `chmod`/atomic-rename semantics do not work — x20, `/google/data`, srcfs/FUSE, or an NFS mount. | Use a **local-disk** review directory: `fetch-cl.sh <CL> <PS> /tmp/cl-<CL>-ps<PS>`. Do not try to work around it by relaxing permissions; every seal in this skill depends on `chmod -w` working. | fetch-cl.sh:670 |
| **`<REVIEW_DIR> is non-empty but has no valid pin.md; use a fresh directory`** | You pointed `fetch-cl.sh` at a directory that already has files but no usable pin — a half-created directory, or an unrelated directory. | Use a new path: `fetch-cl.sh <CL> <PS> /tmp/cl-<CL>-ps<PS>`. Only reuse a directory that `fetch-cl.sh` itself created and that still has a valid `pin.md`. | fetch-cl.sh:316 |
| **`fatal: Unable to create '<repo>/.git/shallow.lock': File exists`** (raw `git` output, usually followed by a `git fetch ... failed` die) | Two `fetch-cl.sh` runs fetched into the same Chromium clone at once, or a previous `git fetch` was killed and left the lock behind. | Wait for the other fetch to finish and retry. If no `git` process is running (`pgrep -af "git.*fetch"` is empty), remove the stale lock: `rm -f <repo>/.git/shallow.lock`, then re-run `fetch-cl.sh`. Serialize concurrent reviews so only one fetches at a time. | observed in run logs, not located in source (emitted by `git`, invoked at fetch-cl.sh:493, :512) |
| `$REVIEW_DIR is pinned to CL <a> PS<b> <sha> (parent <p>), not CL <c> PS<d> <sha2> (parent <q>)` | The directory belongs to a different CL/patchset. | Use a fresh review directory for the new CL/patchset. | fetch-cl.sh:311 |
| `<REVIEW_DIR> has an existing pin but missing pinned detail.json/comments.json; use a fresh review directory or repair it explicitly` | Partially populated review directory. | Use a fresh directory. | fetch-cl.sh:313 |
| `cannot safely identify the existing explicit review directory` | `pin.md` is unparseable. | Use a fresh directory. | fetch-cl.sh:308 |
| `<REVIEW_DIR> lost ownership of its worktree lease (see above); this review must stop. ...` | The lease was taken by another review. | Stop and report to the user. Start a new review directory, or pass `--holder` only with user confirmation. | fetch-cl.sh:360 |
| `could not acquire the CL <n> patchset <p> worktree lease` | Another holder owns the pin. | Run `worktree-lease.py holders <LEASE_DIR>` to see who. Use a distinct `--holder` for a concurrent review. | fetch-cl.sh:400 |
| `timed out after <N>s waiting for the CL <n> patchset <p> worktree materialization lock: <path>` | Another run is materializing the same worktree. | Wait and retry, or raise `CHROMIUM_REVIEW_MATERIALIZE_TIMEOUT`. | fetch-cl.sh:437 |
| `usage: fetch-cl.sh [--force-restart] [--holder KEY] <cl-number> [patchset] [review-dir]` | The CL argument was not numeric. | Pass the bare CL number, e.g. `fetch-cl.sh 5551234 3 /tmp/cl-5551234-ps3`. | fetch-cl.sh:70 |
| `patchset must be a number or 'current'` | Bad patchset argument. | Pass an integer or the literal `current`. | fetch-cl.sh:72 |
| `unknown option: <x>` | Unrecognized flag. | Only `--force-restart` and `--holder KEY` are accepted. | fetch-cl.sh:64 |
| `--holder requires a value` / `holder key must be 1-64 characters of [A-Za-z0-9_-] starting alphanumeric: <h>` | Missing or malformed holder. | Pass e.g. `--holder review1`. | fetch-cl.sh:42, :100, :379 |
| `not inside a git checkout and CHROMIUM_SRC is not set` | No Chromium clone found. | Run from inside the checkout, or export `CHROMIUM_SRC=/usr/local/google/chromium/src`. | fetch-cl.sh:124 |
| `<REPO> is not a git checkout` | `CHROMIUM_SRC` points somewhere wrong. | Point it at the `src` directory of a real clone. | fetch-cl.sh:125 |
| `checkout root is not a depot_tools src directory; set CHROMIUM_CODEREVIEW_ROOT explicitly` | Non-standard layout. | Export `CHROMIUM_CODEREVIEW_ROOT` to a writable cache directory. | fetch-cl.sh:135 |
| `lease helper is missing or not executable: <path>` | `worktree-lease.py` lost its `+x` bit. | Run `chmod +x <path>`. | fetch-cl.sh:129 |
| `failed to fetch change detail from <url>` | Gerrit REST call failed. | Check network/auth, then retry. Raise `CURL_MAX_TIME` if it is a timeout. | fetch-cl.sh:204 |
| `failed to fetch published comments from <url>; unresolved-thread reconciliation would be unsafe` | Comments fetch failed. | Retry; do not proceed without `comments.json`. | fetch-cl.sh:208 |
| `failed to resolve requested patchset from change detail` | The patchset does not exist on that CL. | Pass a valid patchset number, or `current`. | fetch-cl.sh:289 |
| `git fetch <ref> failed (tried sso:// and https)` | Both transports failed. | Check auth (`git credential` / `gcert`), then retry. | fetch-cl.sh:512 |
| `git fetch <ref> failed in Rift workspace` | Fetch failed inside a Rift workspace. | Retry; see the `shallow.lock` row above if the failure mentions a lock. | fetch-cl.sh:493 |
| `pinned SHA <sha> not present after fetch — refusing to guess` | The fetch did not bring down the pinned commit. | Re-run the fetch; if the patchset was replaced on Gerrit, re-fetch the current patchset. | fetch-cl.sh:515 |
| `pinned SHA <sha> not present after fetch in Rift workspace` | Same, under Rift. | Re-run the fetch. | fetch-cl.sh:497 |
| `parent commit <p> is unavailable; cannot compute or review the pinned diff` / `... is still unavailable after fetch` | The parent commit is missing (usually a too-shallow clone). | Re-fetch with a larger `FETCH_DEPTH`, e.g. `FETCH_DEPTH=50 fetch-cl.sh ...`. | fetch-cl.sh:528, :532 |
| `<WT> is at <a>, not pinned SHA <b>; use a fresh review directory` | The cached worktree is at the wrong commit. | Use a fresh review directory. | fetch-cl.sh:449, :444 |
| `<WT> has local or untracked changes; inspect it, then run git -C '<repo>' worktree remove --force '<WT>' only if safe` | Dirty pinned worktree. | Run the quoted command after confirming nothing is needed. | fetch-cl.sh:451 |
| `<WT> exists but is not a worktree registered by <repo>; move it aside or remove it explicitly` | Stray directory at the worktree path. | Move it aside, then re-run. | fetch-cl.sh:447 |
| `<WT> is registered but absent; run 'git -C "<repo>" worktree prune' after checking the path` | Stale worktree registration. | Run the quoted prune command. | fetch-cl.sh:455 |
| `worktree HEAD (<a>) does not match pinned SHA (<b>)` | Post-materialization check failed. | Use a fresh review directory. | fetch-cl.sh:522 |
| `CURL_CONNECT_TIMEOUT / CURL_MAX_TIME / CURL_RETRIES / CHROMIUM_REVIEW_LEASE_SECONDS / CHROMIUM_REVIEW_MATERIALIZE_TIMEOUT / FETCH_DEPTH must be a ... integer` | An env var is non-numeric. | Export a valid integer, or unset it for the default. | fetch-cl.sh:87-92 |
| `<command> is required` | A prerequisite binary is missing. | Install it (typically `curl`, `git`, `python3`, `flock`). | fetch-cl.sh:95 |
| `cannot create <path>` / `mktemp failed` / `cannot create atomic staging directory` / `cannot create unique review directory` | Filesystem is read-only or out of space. | Use a local-disk path such as `/tmp/cl-<CL>-ps<PS>` and check `df`. | fetch-cl.sh:141, :143, :294, :320, :321, :380 |

---
