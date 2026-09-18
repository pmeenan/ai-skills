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

## 6. `snapshot-skill.py`

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| **`snapshot file set differs from manifest; missing=[...], unexpected=[...]`** | The files under `<REVIEW_DIR>/skill-snapshot` no longer match `manifest`. `unexpected=` means extra files appeared (a new reference was copied in, or an editor left a `.swp`/backup); `missing=` means a snapshotted file was deleted. | Re-seal the snapshot: `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR>`. Never add or delete files under `skill-snapshot/` by hand. If the run must stay on the old snapshot, delete only the `unexpected=` files. | snapshot-skill.py:104 |
| `cannot read snapshot manifest <path>: <err>` | Manifest unreadable. | Re-seal with `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR>`. | snapshot-skill.py:79 |
| `invalid snapshot manifest: <err>` | Manifest is not valid JSON. | Re-seal. | snapshot-skill.py:81 |
| `invalid snapshot manifest row in <path>` | A manifest entry is malformed. | Re-seal. | snapshot-skill.py:85 |
| `cannot read snapshotted input <path>: <err>` | A snapshot file is unreadable. | Re-seal. | snapshot-skill.py:92 |
| `snapshotted input changed after sealing: <path>` | A file inside `skill-snapshot/` was edited. | Restore it, or re-seal the snapshot. The snapshot is the workers' immutable copy of the skill. | snapshot-skill.py:94 |
| `not a skill directory: <path>` | First positional arg is not the skill root. | Pass the directory containing `SKILL.md`. | snapshot-skill.py:113 |
| `selected file escapes skill directory: <path>` | A symlink or `..` pointed outside the skill. | Remove the offending link from the skill tree. | snapshot-skill.py:121 |
| `source changed while snapshotting: <path>` | The live skill was edited mid-snapshot. | Stop editing the skill and re-run `snapshot-skill.py`. | snapshot-skill.py:131 |
| `review directory does not exist: <path>` | Bad second positional arg. | Pass the real review directory. | snapshot-skill.py:176 |
| `snapshot destination is not a directory: <path>` | `skill-snapshot` exists as a file. | Remove the file and re-run `snapshot-skill.py`. | snapshot-skill.py:181 |
| `skill snapshot is absent: <path>` (from `--check`) | No snapshot yet. | Run `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR>`. | snapshot-skill.py:184 |
| `timed out waiting for skill snapshot guard: <path>` | Another snapshot run held the lock. | Retry; raise the guard timeout if it recurs. | snapshot-skill.py:54 |
| `<VAR> must be a positive number` | The guard-timeout env var is non-numeric or ≤ 0. | Export a positive number, or unset it. | snapshot-skill.py:44, :46 |

---
