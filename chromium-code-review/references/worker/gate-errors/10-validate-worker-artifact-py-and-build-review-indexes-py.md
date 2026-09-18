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

## 10. `validate-worker-artifact.py` and `build-review-indexes.py`

`validate-review-dir.py` re-runs both of these and re-reports their output as
`<file>: worker-artifact validation failed: <inner message>` (§4.10) or as an
index staleness error (§4.1). Fix the inner message here.

### 10a. `validate-worker-artifact.py`

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `review directory does not exist: <p>` / `artifact does not exist: <p>` | Bad arguments. | Pass real paths. | validate-worker-artifact.py:635, :637 |
| `artifact is outside review directory: <p>` | Artifact escapes the review root. | Put the artifact under `<REVIEW_DIR>/`. | validate-worker-artifact.py:639 |
| `cannot read <p>: <err>` | Unreadable or non-UTF-8. | Re-save as UTF-8. | validate-worker-artifact.py:643 |
| `<f> lacks exact '<heading>' heading` | A required `##` heading is missing or reworded. | Add the heading exactly as written in `references/templates.md`. | validate-worker-artifact.py:205, :416, :543, :130 |
| `<f> Candidate descriptors table has wrong columns` | Header mismatch. | Use the `DESCRIPTOR_COLUMNS` header from §4.10. | validate-worker-artifact.py:120 |
| `<f> duplicates Candidate descriptors for <c>` | Duplicate descriptor rows. | Keep one row per candidate. | validate-worker-artifact.py:124 |
| `<f> has descriptors for non-candidates: <ids>` | Descriptors for non-candidate rows. | Remove them. | validate-worker-artifact.py:132 |
| `<f> candidate <c> has no descriptor row` | Missing descriptor. | Add it. | validate-worker-artifact.py:139 |
| `<f> candidate <c> has invalid classes: <x>` | Bad class token. | Use the class list in §1. | validate-worker-artifact.py:145 |
| `<f> candidate <c> has invalid obligations: <x>` | Bad obligation token. | Use the obligations list in §1. | validate-worker-artifact.py:150 |
| `<f> candidate <c> lacks class-required obligations: <x>` | Class implies obligations you omitted. | Add them. | validate-worker-artifact.py:157 |
| `<f> candidate <c> has unresolved descriptor '<cell>'; use 'unknown — reason' when the answer is genuinely not known yet` | Placeholder descriptor cell. | Write the value, or `unknown — <specific reason>`. | validate-worker-artifact.py:164 |
| `<f> compliance matrix has wrong columns` | Header mismatch. | Copy the compliance-matrix header from the template. | validate-worker-artifact.py:209 |
| `<f> compliance matrix row <r> has a blank answer/evidence` | Empty cell. | Fill both cells. | validate-worker-artifact.py:214 |
| `<f> compliance matrix row <r> is a citation-free PASS` | `PASS` with no `path:line`. | Add a citation. | validate-worker-artifact.py:221 |
| `<f> compliance matrix row <r> has N/A without a reason` | Bare `N/A`. | Write `N/A — <reason>`. | validate-worker-artifact.py:228 |
| `<f> <table> table has no id column` | Missing `id` column. | Add it. | validate-worker-artifact.py:234 |
| `<f> has invalid row ID '<id>'` | ID does not match `ROW_ID`. | Use `<PREFIX>-<n>`. | validate-worker-artifact.py:238 |
| `<f> must have exactly one 'Specialist escalation assessments' table` | Zero or several. | Keep exactly one. | validate-worker-artifact.py:245 |
| `<f> specialist assessment table has wrong columns` | Header mismatch. | Copy the header from the template. | validate-worker-artifact.py:255 |
| `<f> duplicates specialist assessment for <lens>` | Duplicate row. | Keep one row per lens. | validate-worker-artifact.py:260 |
| `<f> specialist assessments have missing/unknown lenses: missing=<a>; unknown=<b>` | Lens set does not equal `SPECIALIST_LENSES`. | Assess all ten lenses, using the exact names from §1. | validate-worker-artifact.py:265 |
| `<f> specialist assessments must share one exact assigned graph scope` | Rows use different scopes. | Use the generalist's single assigned graph scope on every row. | validate-worker-artifact.py:275 |
| `<f> <lens> must use low, medium, or high` | Bad likelihood token. | Use `low`, `medium`, or `high`. | validate-worker-artifact.py:284 |
| `<f> <lens> has invalid exact graph scope` | Scope is not `graph:<edge-ids>` or `graph:none`. | Write exact edge IDs. | validate-worker-artifact.py:291 |
| `<f> <lens> lacks cited signals/counterevidence` | No citations. | Cite `path:line` evidence on both sides. | validate-worker-artifact.py:297 |
| `<f> <lens> low likelihood lacks cited counterevidence` | `low` with no counterevidence. | Cite what rules the lens out. | validate-worker-artifact.py:303 |
| `<f> <lens> likelihood lacks cited positive signals` | `medium`/`high` with no positive signal. | Cite the signal that raises the likelihood. | validate-worker-artifact.py:309 |
| `<f> <lens> graph:none assessment must be low; a higher likelihood requires an inventory edge` | `graph:none` with `medium`/`high`. | Either lower it to `low`, or cite real inventory edges. | validate-worker-artifact.py:311 |
| `<f> has duplicate Specialist probe outcome tables` | More than one. | Keep exactly one. | validate-worker-artifact.py:321 |
| `<f> has malformed Specialist probe outcome` | Wrong table shape. | Copy the probe-outcome table from the template. | validate-worker-artifact.py:327 |
| `<f> probe result must be clean or escalate` | Free-text result. | Write `clean` or `escalate`. | validate-worker-artifact.py:333 |
| `<f> probe outcome lacks cited evidence` | No citation. | Add `path:line`. | validate-worker-artifact.py:335 |
| `<f> clean probe must have no remaining scope` | Remaining scope on a clean probe. | Clear it. | validate-worker-artifact.py:337 |
| `<f> escalated probe lacks full remaining graph scope` | Escalation narrowed scope. | Keep the full assigned scope. | validate-worker-artifact.py:343 |
| `<f> cannot validate trace closure without <x>` / `<f> cannot validate families without <x>` | A prerequisite section/artifact is missing. | Add the named section first. | validate-worker-artifact.py:354, :461 |
| `<f> Trace closure table has wrong columns` | Header mismatch. | Copy the header from the template. | validate-worker-artifact.py:374 |
| `<f> candidate <c> has unknown trace obligation '<o>'` | Bad obligation token. | Use the obligations list in §1. | validate-worker-artifact.py:381 |
| `<f> duplicates trace obligation <o> for <c>` | Duplicate row. | Keep one row per (candidate, obligation). | validate-worker-artifact.py:386 |
| `<f> candidate <c> has invalid trace result '<r>'` | Bad result token. | Use `PROVES CANDIDATE`, `REFUTES CANDIDATE`, or `OPEN`. | validate-worker-artifact.py:394 |
| `<f> candidate <c> obligation <o> lacks path:line evidence or an evidence-exception` | Uncited obligation. | Add a citation or an `evidence-exception:`. | validate-worker-artifact.py:402 |
| `<f> Verified affinity table has wrong columns` | Header mismatch. | Copy the header from the template. | validate-worker-artifact.py:410 |
| `<f> verdict targets unknown candidate <c>` | Bad candidate ID. | Correct it. | validate-worker-artifact.py:420 |
| `<f> candidate <c> trace closure mismatch: missing=<a>, foreign=<b>` | Obligation set does not match the descriptor's classes. | Align the trace-closure rows with the descriptor's obligations. | validate-worker-artifact.py:424 |
| `<f> candidate <c> has no Verified affinity row` | Missing affinity row. | Add it. | validate-worker-artifact.py:430 |
| `<f> CONFIRMED candidate <c> has no trace obligation that PROVES CANDIDATE` | Verdict unsupported. | Add the proving obligation, or change the verdict. | validate-worker-artifact.py:433 |
| `<f> REFUTED candidate <c> has no trace obligation that REFUTES CANDIDATE` | Verdict unsupported. | Add the refuting obligation, or change the verdict. | validate-worker-artifact.py:438 |
| `<f> UNPROVEN candidate <c> has no OPEN trace obligation` | `UNPROVEN` with everything closed. | Mark the genuinely open obligation `OPEN`, or pick a decisive verdict. | validate-worker-artifact.py:443 |
| `<f> <v> candidate <c> still has an OPEN trace obligation` | Decisive verdict with an open obligation. | Close the obligation, or downgrade to `UNPROVEN`. | validate-worker-artifact.py:448 |
| `<f> Root families table has wrong columns` / `has invalid root family '<id>'` / `root family <id> has no members` / `... unknown member <m>` / `row <r> belongs to both <a> and <b>` / `root family <id> has blank <col>` | Same family checks as §4.11, run at worker level. | Apply the §4.11 fixes. | validate-worker-artifact.py:494, :498, :501, :504, :509, :516 |
| `<f> Consistency audit table has wrong columns` / `has unknown consistency check '<c>'` / `consistency check '<c>' has no result` / `... lacks code/artifact evidence or evidence-exception` / `... occurs <n> times` | Same audit checks as §4.11. | Apply the §4.11 fixes. | validate-worker-artifact.py:523, :529, :531, :537, :546 |
| `<f> surviving candidate/verdict <c>/<v> is not fully assigned` / `... is split across root families` | Same as §4.11. | Assign each survivor to exactly one family. | validate-worker-artifact.py:552, :557 |
| `<f> has <n> effective roster tables; expected exactly one` | Zero or several roster tables. | Keep exactly one. | validate-worker-artifact.py:573 |
| `<f> roster must have exactly the ordered columns <cols>` | Header mismatch. | Copy the roster header. | validate-worker-artifact.py:579 |
| `<f> roster has no rows` / `<f> has a blank roster entry` | Empty roster. | Fill in the roster rows. | validate-worker-artifact.py:584, :592 |
| `<f> has malformed shard label '<l>'` | Bad shard suffix. | Use `<Thread Name> <n>`. | validate-worker-artifact.py:594 |
| `<f> duplicates effective plan identity <x>` | Duplicate row identity. | De-duplicate. | validate-worker-artifact.py:597 |
| `<f> plan row '<r>' has invalid status '<s>'` | Bad status. | Use the template's status vocabulary. | validate-worker-artifact.py:609 |
| `<f> mixes sharded and unsharded effective rows for <name>` | Mixed sharding. | Shard all or none. | validate-worker-artifact.py:613 |

### 10b. `build-review-indexes.py`

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `missing or stale output: <path>` (from `--check`) | A derived index is out of date. | Run `build-review-indexes.py <REVIEW_DIR>` (no `--check`) to regenerate. | build-review-indexes.py:908 |
| `review directory does not exist: <p>` | Bad argument. | Pass the real review directory. | build-review-indexes.py:850 |
| `cannot read <p>: <err>` | Unreadable input. | Re-save as UTF-8. | build-review-indexes.py:81 |
| `missing inventory ID in <f>` | An inventory row has no ID. | Add the ID. | build-review-indexes.py:94 |
| `duplicate inventory ID <id> in <a> and <b>` | Two shards reused an ID. | Prefix per-shard IDs. | build-review-indexes.py:97 |
| `<f>: descending hunk range '<r>'` | `start > end`. | Swap the endpoints. | build-review-indexes.py:136 |
| `<f>: hunk range endpoint <n> is not in profile.json` | Hunk number unknown to the profile. | Use hunk numbers from `profile.json`; regenerate the profile if the CL changed. | build-review-indexes.py:144 |
| `<f>: implausible hunk range '<r>'` | Range is absurdly wide. | Correct the range. | build-review-indexes.py:149 |
| `<f>: surface <s> must name exactly one full repo-relative path after '/' in its owned-hunks cell` | Owned-hunks cell names zero or several paths. | Name exactly one repo-relative path. | build-review-indexes.py:158 |
| `hunk <h> is claimed by both <a> and <b>; shard hunk ownership must be disjoint` | Overlapping shards. | Make hunk ownership disjoint. | build-review-indexes.py:167 |
| `<f>: hunk <h> belongs to <a> but the surface row cites <b>` | Wrong file cited for a hunk. | Cite the file the hunk actually belongs to. | build-review-indexes.py:174 |
| `<f>: group surface '<s>' lacks a leading member count (shape: 'group: <N> ...')` | Group surface missing its count. | Write `group: <N> <description>`. | build-review-indexes.py:184 |
| `inventory claims unknown hunk <h> absent from profile.json` | Hunk not in the profile. | Regenerate `profile.json`, or correct the hunk number. | build-review-indexes.py:224 |
| `sharded inventory leaves hunk <h> with no owning surface row` | Incomplete shard coverage. | Add a surface row owning that hunk. | build-review-indexes.py:229 |
| `<f>: Complexity graph edges lacks required columns` | Header mismatch. | Copy the header from the template. | build-review-indexes.py:248 |
| `<f>: invalid graph edge ID '<id>'` | Bad edge ID. | Use the `E-<n>` form from the template. | build-review-indexes.py:255 |
| `duplicate graph edge <id>` | Two rows for one edge. | De-duplicate. | build-review-indexes.py:257 |
| `<f>: graph edge <id> has invalid kind '<k>'` / `invalid status '<s>'` | Bad token. | Use the template's kind/status vocabulary. | build-review-indexes.py:259, :261 |
| `<f>: graph edge <id> lacks evidence` | No citation. | Add `path:line`. | build-review-indexes.py:263 |
| `<f>: Complexity graph delta lacks required columns` | Header mismatch. | Copy the header. | build-review-indexes.py:278 |
| `<f>: graph delta targets unknown edge <id>` | Delta for a nonexistent edge. | Correct the edge ID. | build-review-indexes.py:282 |
| `<f>: graph delta <id> has invalid status '<s>'` / `lacks evidence` | Bad status or no citation. | Fix the status token; add `path:line`. | build-review-indexes.py:286, :288 |
| `<f>: Specialist escalation assessments lacks required columns` | Header mismatch. | Copy the header. | build-review-indexes.py:353 |
| `<f>: unknown specialist lens '<l>'` | Lens name not in `SPECIALIST_LENSES`. | Use the exact lens name from §1. | build-review-indexes.py:364 |
| `<f>: <lens> has invalid likelihood '<v>'; use low, medium, or high` | Bad likelihood. | Use `low`, `medium`, or `high`. | build-review-indexes.py:366 |
| `<f>: <lens> graph scope must be exact graph:E-... edge IDs, or graph:none for a zero-edge inventory` | Scope is not exact. | Write `graph:E-1,E-2` (or `graph:none` only when the inventory has no edges). | build-review-indexes.py:375 |
| `<f>: <lens> may use graph:none only when the inventory has zero graph edges` | `graph:none` with edges present. | Cite the real edges. | build-review-indexes.py:381 |
| `<f>: <lens> graph scope repeats an edge` | Duplicate edge in the scope. | De-duplicate. | build-review-indexes.py:390 |
| `<f>: <lens> cites unknown graph edge(s): <ids>` | Bad edge IDs. | Correct them against the edges table. | build-review-indexes.py:393 |
| `<f>: <lens> lacks assessed signals` / `lacks assessed counterevidence` | Empty cell. | Fill both cells. | build-review-indexes.py:398, :400 |
| `<f>: <lens> likelihood lacks cited evidence` / `low likelihood lacks cited counterevidence` / `<v> likelihood lacks cited positive signals` / `<v> likelihood lacks a positive signal` | Uncited assessment. | Cite `path:line` evidence supporting the stated likelihood. | build-review-indexes.py:403, :410, :418, :425 |
| `<f>: <lens> graph:none assessment must be low; a higher likelihood requires an inventory edge` | `graph:none` with `medium`/`high`. | Lower it to `low`, or cite edges. | build-review-indexes.py:430 |
| `duplicate <k> specialist assessment for <lens> <scope> in <a> and <b>` | Two ledgers assessed the same lens/scope. | Keep one. | build-review-indexes.py:436 |
| `<f>: generalist ledger lacks ## Specialist escalation assessments` | Section missing. | Add the section. | build-review-indexes.py:449 |
| `<f>: generalist ledger lacks specialist assessment(s): <lenses>` | Lenses unassessed. | Assess every lens. | build-review-indexes.py:455 |
| `<f>: generalist specialist assessments must share one exact assigned graph scope` | Mixed scopes. | Use the single assigned scope on every row. | build-review-indexes.py:460 |
| `<f>: duplicate Candidate descriptors row for <c>` | Duplicate descriptor. | Keep one. | build-review-indexes.py:489 |
| `duplicate candidate ID <c> in <a> and <b>` | Reused candidate ID across ledgers. | Prefix IDs per thread. | build-review-indexes.py:511 |
| `<f>: candidate <c> has no Candidate descriptors row` | Missing descriptor. | Add it. | build-review-indexes.py:528 |
| `<f>: row <r> belongs to both <a> and <b>` | Row in two families. | Assign to one. | build-review-indexes.py:567 |
| `duplicate verdict ID <v> in <a> and <b>` | Reused verdict ID. | Renumber. | build-review-indexes.py:605 |
| `duplicate canonical row <r> in <a> and <b>` | Reused canonical row ID. | Renumber. | build-review-indexes.py:637 |
| `<f>: malformed merge proposal for '<r>'` | Bad merge syntax in a ledger. | Write `merged → <ROW-ID>`. | build-review-indexes.py:710 |
| `<f>: duplicate merge proposal for <r>` | Duplicate proposal. | Keep one. | build-review-indexes.py:713 |
| `<f>: merge proposal <a> -> <b> references an unknown canonical row` | Bad survivor ID. | Correct it. | build-review-indexes.py:715 |
| `duplicate reconciliation row <r>` | Duplicate row. | Keep one. | build-review-indexes.py:731 |

### 10c. `refresh-delivery-gate.py`

These surface as a Python traceback ending in `ValueError: <message>`.

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `pin.md lacks a CL number, pinned patchset, or full revision SHA` | `pin.md` is malformed. | Regenerate it with `fetch-cl.sh`. | refresh-delivery-gate.py:90 |
| `Gerrit detail fetch failed after 3 attempts: <err>` | Gerrit unreachable. | Retry, or pass a pre-fetched file with `--detail-json <path>`. | refresh-delivery-gate.py:53 |
| `<source> contains only a Gerrit XSSI prefix` | The detail JSON is just `)]}'`. | Re-fetch; the download was truncated. | refresh-delivery-gate.py:34 |
| `<source> must contain a JSON object` | Wrong JSON shape. | Re-fetch the detail JSON. | refresh-delivery-gate.py:38 |
| `detail has no ALL_REVISIONS map or full current_revision` | Detail fetched without `ALL_REVISIONS`. | Let the script fetch it itself, or pass a detail JSON fetched with `o=ALL_REVISIONS`. | refresh-delivery-gate.py:100 |
| `detail current_revision is absent from revisions or lacks _number` | Inconsistent Gerrit response. | Re-fetch the detail JSON. | refresh-delivery-gate.py:103 |
| `pinned SHA does not map to the pinned patchset in ALL_REVISIONS` | `pin.md` and Gerrit disagree. | Re-fetch the CL into a fresh review directory. | refresh-delivery-gate.py:204 |

---
