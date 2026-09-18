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

## 9. `build-phase-brief.py`

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| **`Could not find template for <name> in phase-briefs.md`** | The requested brief name has no matching template heading in `references/phase-briefs.md`. Almost always a name typo or an invented phase name. | List the real template names first, then re-run with an exact match. The lookup is literal — `inventory` will not match a heading called `Inventory pass`. | build-phase-brief.py:99 |
| `missing phase-briefs.md at <path>` | The reference file is absent from the snapshot. | Re-run `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR>`, then retry. | build-phase-brief.py:85 |
| `missing required common header template in <path>` | `phase-briefs.md` has no common header block. | Re-snapshot the skill; do not hand-edit the snapshot. | build-phase-brief.py:79 |
| `could not find fenced ```text block in template` | The matched template has no ```text fence. | Fix the template in `references/phase-briefs.md` (a fenced ```text block is required). | build-phase-brief.py:20 |
| `missing pin.md at <path>` | No pin in the review directory. | Run `fetch-cl.sh <CL> <PS> <REVIEW_DIR>` first. | build-phase-brief.py:26 |
| `could not parse CL/patchset from pin.md` | `pin.md` header is malformed. | Regenerate `pin.md` with `fetch-cl.sh`. | build-phase-brief.py:30 |
| `could not parse SHA/worktree fields from pin.md` | Same. | Regenerate `pin.md` with `fetch-cl.sh`. | build-phase-brief.py:38 |
| `missing skill-snapshot at <path>` | No sealed snapshot. | Run `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR>`. | build-phase-brief.py:71 |

---
