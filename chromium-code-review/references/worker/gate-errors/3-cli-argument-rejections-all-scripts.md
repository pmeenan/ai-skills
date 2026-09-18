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

## 3. CLI argument rejections (all scripts)

These come from `argparse`, before any validation runs. The text is verbatim
from running the scripts.

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `argument --phase: invalid choice: 'inventory' (choose from 'auto', 'pin', 'collection', 'verification', 'reconciliation', 'final')` | You passed a workflow-stage name (`inventory`, `planning`, `plan`, `phase 1`, `discovery`) that is not one of the five validator phases. Inventory and planning both live inside the `collection` phase. | Run `validate-review-dir.py <REVIEW_DIR> --phase collection`, or omit `--phase` entirely to let `infer_phase()` pick. | argparse output (verified by running the script); choices at validate-review-dir.py:5198, `PHASES` at :34, `infer_phase` at :5183 |
| `argument command: invalid choice: 'status' (choose from 'acquire', 'write-state', 'validate-state', 'heartbeat', 'release', 'release-token', 'check', 'holder-of', 'holders', 'gc')` | `worktree-lease.py` has no `status` or `progress` subcommand. | For "is my lease still good?" run `worktree-lease.py check <REVIEW_DIR>`. To record progress run `worktree-lease.py heartbeat <REVIEW_DIR> "<message>"`. To see who holds a pin run `worktree-lease.py holders <LEASE_DIR>`. | argparse output (verified by running the script); subparsers at worktree-lease.py:916-975 |
| `argument --tier: invalid choice: 'premium' (choose from 'frontier', 'inherit', 'mechanical', 'standard')` | `seal-work-unit.py --tier` takes only the four `TIERS` values. | Pass one of `mechanical`, `standard`, `frontier`, `inherit`. | argparse output (verified by running the script); `TIERS` at seal-work-unit.py:35, `choices=` at :192 |
| `validate-review-dir.py: ERROR: not a directory: <path>` (exit 2) | The positional `review_dir` does not resolve to a directory. | Pass the review directory itself, not a file inside it. | validate-review-dir.py:5206 |
| `--input must be ROLE=/absolute/path with role in ['assigned', 'candidate-packet', 'card', 'control', 'frame', 'prestate', 'reference', 'section']` | `--input` was not `ROLE=path`, or the role is not in `ROLES`. | Re-pass as `--input assigned=/abs/path`. Note `brief` is **not** a legal `--input` role; the brief is passed with `--brief`. | seal-work-unit.py:135 |
| `--stdout and --check are mutually exclusive` | `profile-review.py` got both flags. | Pick one. | profile-review.py:581 |

---
