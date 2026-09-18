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

## 5. `seal-work-unit.py`

All messages print as `seal-work-unit.py: ERROR: <message>` and exit 1.

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| **`attempt already exists but does not match the requested seal: ('CH001', '4'); inspect the queued row instead of incrementing the attempt`** | `(work_id, attempt)` is already in `orchestration.tsv`/`input-manifest.tsv`, but with *different* values (different brief, artifact, tier, phase, depends_on, remaining_scope, or a different input set). Re-sealing the same key with the same values is idempotent and prints `already sealed ...`. | Print the existing row: `awk -F'\t' '$2=="CH001" && $3=="4"' <REVIEW_DIR>/orchestration.tsv` and diff it against your command. Then either re-issue the **identical** original command, or — if the work genuinely changed — seal it as the **next** attempt with an attempt-specific brief. Do **not** delete the queued row, and do not blindly bump the attempt: the message is telling you the existing row is the source of truth. | seal-work-unit.py:303 |
| `already sealed <work>:<attempt> <brief>` *(success, exit 0)* | Idempotent replay of an identical seal. | Nothing; treat as success. | seal-work-unit.py:298 |
| **`reference input is not from the sealed skill snapshot: <path>`** | `--input reference=<path>` pointed outside `<REVIEW_DIR>/skill-snapshot/`. Workers may only read skill docs through the snapshot, never the live skill tree. | Re-run `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR>` if needed, then pass `--input reference=<REVIEW_DIR>/skill-snapshot/references/<file>.md`. | seal-work-unit.py:238 |
| **`timed out waiting for orchestration mutation guard: <REVIEW_DIR>/.orchestration.lock`** | Another `seal-work-unit.py` held the flock past the timeout (30s by default). | Wait for the other seal to finish and retry. If nothing is running, raise the timeout for one invocation: `CHROMIUM_REVIEW_GUARD_SECONDS=120 seal-work-unit.py ...`. Do not delete `.orchestration.lock`. | seal-work-unit.py:104, :36 |
| `CHROMIUM_REVIEW_GUARD_SECONDS must be a positive number` | The env var is unset-but-empty, non-numeric, or ≤ 0. | Export a positive number, or unset it to get the 30s default. | seal-work-unit.py:94, :96 |
| `<path> has wrong columns or order` | `orchestration.tsv` or `input-manifest.tsv` header does not match the tuple in §1. | Restore the exact header; never reorder columns. | seal-work-unit.py:82 |
| `cannot parse <path>: <err>` | TSV is corrupt. | Restore the file from its last good state; do not hand-edit. | seal-work-unit.py:85 |
| `cannot recover interrupted seal transaction <journal>: <err>` | `.work-unit-seal-transaction.json` is unreadable. | Inspect the journal file; if it is truncated garbage, delete it **only** after confirming neither TSV was partially written, then re-run the original seal. | seal-work-unit.py:126 |
| `--input must be ROLE=/absolute/path with role in [...]` | Malformed `--input`. | See §3. | seal-work-unit.py:135 |
| `input path must be absolute: <path>` | Relative input path. | Pass an absolute path. | seal-work-unit.py:138 |
| `input does not exist: <path>` | Input file missing. | Create the input before sealing. | seal-work-unit.py:141 |
| `cannot read <profile_path>: <err>` | `profile.json` unreadable. | Run `profile-review.py <REVIEW_DIR>`. | seal-work-unit.py:154 |
| `work unit inputs exceed budget (<total> > <limit> bytes)` | Sealed inputs exceed the tier (or global) worker-input budget. | Shard the work unit, or drop inputs. Raising the budget in `profile.json` is a last resort. | seal-work-unit.py:166 |
| `candidate packet inputs exceed budget (<total> > <limit> bytes)` | `candidate-packet` inputs alone exceed their budget. | Split the packet across work units. | seal-work-unit.py:172 |
| `review directory does not exist: <path>` | Bad positional arg. | Pass the real review directory. | seal-work-unit.py:207 |
| `--attempt must be positive` | `--attempt 0` or negative. | Start at `--attempt 1`. | seal-work-unit.py:209 |
| `--work-id is invalid` | Empty, or contains tab/CR/LF. | Use a short token like `CH001`. | seal-work-unit.py:211 |
| `--brief and --artifact must be absolute` | Relative paths. | Pass absolute paths. | seal-work-unit.py:215 |
| `brief must be an existing file inside the review: <path>` | Brief is missing or outside the review directory. | Write the brief under `<REVIEW_DIR>/briefs/`. | seal-work-unit.py:219 |
| `artifact must be inside the review: <path>` | Artifact path escapes the review directory. | Point `--artifact` at `<REVIEW_DIR>/ledger/<ID>.md` (or the appropriate subdirectory). | seal-work-unit.py:221 |
| `skill snapshot is absent or stale: <detail>` | `snapshot-skill.py --check` failed. | Run `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR>`, then re-seal. | seal-work-unit.py:229 |
| `an input role/path is listed more than once` | Duplicate `(role, path)` in `--input`, or an `--input` that repeats the `--brief`. | Remove the duplicate; the brief is added automatically as the `brief` self row. | seal-work-unit.py:241 |
| `brief changed while sealing: <path>` / `brief changed while restoring its seal: <path>` | The brief was modified between read and chmod. | Stop editing the brief; re-run the seal once the file is final. | seal-work-unit.py:314, :297 |

> [!IMPORTANT]
> `seal-work-unit.py` makes the brief read-only (`chmod -w`) as its last step.
> Once sealed, a brief may not be edited — write a **new** attempt-specific
> brief for a continuation.

---
