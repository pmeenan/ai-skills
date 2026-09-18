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

## 2. Fast index for the failures seen most often

| Message (substring you will actually see) | Go to |
| --- | --- |
| `--phase: invalid choice: 'inventory'` (also `planning`, `plan`, `phase 1`) | [§3 CLI](#3-cli-argument-rejections-all-scripts) |
| `invalid choice: 'status'` / `'progress'` from `worktree-lease.py` | [§3 CLI](#3-cli-argument-rejections-all-scripts) |
| `input-manifest.tsv:<N>: byte count mismatch` | [§4 validate-review-dir](#46-input-manifesttsv-validate_input_manifest) |
| `prestate prefix hash mismatch` | [§4 validate-review-dir](#46-input-manifesttsv-validate_input_manifest) |
| `names input <X> in Inputs/Procedure but input-manifest.tsv omits it` | [§4 validate-review-dir](#46-input-manifesttsv-validate_input_manifest) |
| `attempt already exists but does not match the requested seal` | [§5 seal-work-unit](#5-seal-work-unitpy) |
| `is a frontier-contract kind but an attempt recorded tier` | [§4 validate-review-dir](#47-orchestrationtsv-validate_manifest) |
| `reference input is not from the sealed skill snapshot` | [§5 seal-work-unit](#5-seal-work-unitpy) |
| `snapshot file set differs from manifest; ... unexpected=` | [§6 snapshot-skill](#6-snapshot-skillpy) |
| `lease is stale (<N>s since progress; limit 3600s)` | [§7 worktree-lease](#7-worktree-leasepy) |
| `lease expired <N>s after its last progress` | [§7 worktree-lease](#7-worktree-leasepy) |
| `could not persist authenticated mutable lease state` | [§8 fetch-cl.sh](#8-fetch-clsh) |
| `is non-empty but has no valid pin.md` | [§8 fetch-cl.sh](#8-fetch-clsh) |
| `timed out waiting for orchestration mutation guard` | [§5 seal-work-unit](#5-seal-work-unitpy) |
| `timed out waiting for lease mutation guard` | [§7 worktree-lease](#7-worktree-leasepy) |
| `Unable to create '<repo>/.git/shallow.lock': File exists` | [§8 fetch-cl.sh](#8-fetch-clsh) |
| `Could not find template for <name> in phase-briefs.md` | [§9 build-phase-brief](#9-build-phase-briefpy) |
| suggestion-block fence / indentation complaints | [§11 suggestion blocks](#11-suggestion-block-and-placeholder-rules) |
| `gerrit-comments.md contains a local path/URL or placeholder inline` | [§11 suggestion blocks](#11-suggestion-block-and-placeholder-rules) |

---
