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

## 4. `validate-review-dir.py`

Every row below is an `ERROR:` unless marked *(warning)*. Warnings do not fail
the gate.

### 4.1 Reading artifacts, profile, snapshot, table contracts

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `missing required artifact: <path>` | A file the current phase requires is absent. | Create the named file, or re-run at a lower `--phase`. | validate-review-dir.py:286, :598 |
| `cannot read <path>: <err>` | Unreadable or non-UTF-8 file. | Re-write the file as UTF-8. | validate-review-dir.py:288 |
| `invalid JSON in <path>: <err>` | JSON artifact does not parse. | Re-fetch with `fetch-cl.sh`, or fix the JSON. | validate-review-dir.py:600 |
| `<path> still contains Gerrit's XSSI prefix` | The `)]}'` line was not stripped from a Gerrit JSON download. | Re-run `fetch-cl.sh`; do not hand-download Gerrit JSON. | validate-review-dir.py:594 |
| `plan.md roster table must have exactly the ordered columns <cols>` | Roster header does not match `PLAN_ROSTER_COLUMNS`. | Copy the header row from the plan template in `references/templates.md`. | validate-review-dir.py:665 |
| `cannot run <script> --check: <err>` | A subprocess (`profile-review.py` / `build-review-indexes.py`) failed to launch. | Run the named script manually to see the real error. | validate-review-dir.py:718 |
| `<script> --check failed: <err>` | Derived outputs are stale relative to their inputs. | Re-run the named script without `--check` to regenerate. | validate-review-dir.py:722 |
| `profile.json lacks context_budget object` | `profile.json` is truncated or hand-edited. | Regenerate: `profile-review.py <REVIEW_DIR>`. | validate-review-dir.py:732 |
| `profile.json context_budget has invalid <key>` | A budget key is missing or not a positive int. | Regenerate `profile.json`; do not hand-edit budgets. | validate-review-dir.py:741 |
| `profile.json tier_worker_input_budget_bytes has invalid entry <k>` | Per-tier budget map has a bad key/value. | Regenerate `profile.json`. | validate-review-dir.py:751 |
| `profile.json <key> exceeds worker_input_budget_bytes` | A per-tier budget is larger than the global cap. | Regenerate `profile.json`; lower the per-tier override. | validate-review-dir.py:757 |
| `cannot run skill snapshot validator: <err>` | `snapshot-skill.py` could not be executed. | Run `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR> --check` directly. | validate-review-dir.py:770 |
| `skill snapshot is absent or stale: <detail>` | `<REVIEW_DIR>/skill-snapshot` is missing or no longer matches the live skill. | Run `snapshot-skill.py <SKILL_DIR> <REVIEW_DIR>` to re-seal, then re-run the gate. | validate-review-dir.py:774 |

### 4.2 `pin.md`, pinned worktree, and lease (`validate_pin`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `detail.json must contain an object` | `detail.json` is an array or scalar. | Re-run `fetch-cl.sh <CL> <PS>`. | validate-review-dir.py:783 |
| `comments.json must contain a path-to-arrays object` | `comments.json` shape is wrong. | Re-run `fetch-cl.sh`. | validate-review-dir.py:786 |
| `comments.json must map every path string to an array` | One path key maps to a non-array. | Re-run `fetch-cl.sh`. | validate-review-dir.py:790 |
| `pin.md is missing '- <field>:'` | A required `- Field:` line is absent from `pin.md`. | Add the exact `- <field>:` line; regenerate with `fetch-cl.sh` rather than editing by hand. | validate-review-dir.py:806 |
| `pin.md Revision SHA is not a full hexadecimal object id` | Abbreviated or non-hex SHA. | Put the full 40-char SHA in `- Revision SHA:`. | validate-review-dir.py:808 |
| `pin.md Parent SHA is not a full hexadecimal object id` | Same, for the parent. | Put the full 40-char parent SHA in. | validate-review-dir.py:810 |
| `pin.md Is current at fetch must be yes or no` | Free-text value in that field. | Set it to exactly `yes` or `no`. | validate-review-dir.py:812 |
| `pin.md Is current at fetch is <x>, expected <y>` | The field contradicts `detail.json`. | Re-run `fetch-cl.sh` to re-derive it. | validate-review-dir.py:816 |
| `pin.md Revision SHA is absent from detail.json revisions` | The pin points at a revision Gerrit does not list. | Re-run `fetch-cl.sh <CL> <PS>` into a fresh review directory. | validate-review-dir.py:820 |
| `pin.md patchset does not match detail.json revision number` | Patchset number and SHA disagree. | Re-run `fetch-cl.sh <CL> <PS>` into a fresh review directory. | validate-review-dir.py:824 |
| `pin.md Gerrit-current patchset does not match detail.json` | The recorded "Gerrit current" drifted. | Run `refresh-delivery-gate.py <REVIEW_DIR>` to refresh, or re-fetch. | validate-review-dir.py:829 |
| `pin.md Gerrit-current revision SHA does not match detail.json` | Same, for the SHA. | Run `refresh-delivery-gate.py <REVIEW_DIR>`. | validate-review-dir.py:831 |
| `pinned worktree does not exist: <path>` | The `- Worktree:` path is gone. | Re-run `fetch-cl.sh <CL> <PS> <REVIEW_DIR>` to re-materialize it. | validate-review-dir.py:837 |
| `worktree HEAD <a> does not match pin <b>` | Someone checked the worktree out elsewhere. | Run `git -C <worktree> checkout --detach <pinned-sha>`. | validate-review-dir.py:845 |
| `pinned worktree has local or untracked changes` | The read-only worktree was modified. | Run `git -C <worktree> status` then `git -C <worktree> checkout -- .` and remove untracked files. Never edit the pinned worktree. | validate-review-dir.py:851 |
| `cannot verify pinned worktree: <err>` | `git` failed inside the worktree. | Re-materialize with `fetch-cl.sh`. | validate-review-dir.py:853 |
| `pin.md is missing '- Worktree:'` | No worktree line. | Regenerate `pin.md` with `fetch-cl.sh`. | validate-review-dir.py:855 |
| `pin.md must contain both Worktree lease and Worktree lease token` | Only one of the two lease lines is present. | Re-acquire: `worktree-lease.py acquire <LEASE_DIR> --review-dir <REVIEW_DIR> --holder <KEY>`, then re-run `fetch-cl.sh` to rewrite `pin.md`. | validate-review-dir.py:860 |
| `pin.md requires authenticated lease-state.json, but it is absent` | `pin.md` advertises a lease but `lease-state.json` is missing. | Run `worktree-lease.py write-state <REVIEW_DIR> <LEASE_DIR>/<HOLDER>.log <TOKEN> <HOLDER>`. | validate-review-dir.py:865 |
| `cannot validate authenticated mutable lease state: <err>` | `worktree-lease.py validate-state` could not run. | Run `worktree-lease.py validate-state <REVIEW_DIR>` directly. | validate-review-dir.py:872 |
| `mutable lease state validation failed: <detail>` | `lease-state.json` does not authenticate against this review/pin. | See §7; usually re-run `worktree-lease.py write-state ...` with the real token. | validate-review-dir.py:877 |
| `active worktree lease is required but absent from pin.md` | `--require-active-lease` was passed but `pin.md` has no lease. | Acquire a lease first, or drop `--require-active-lease`. | validate-review-dir.py:880 |
| `cannot run active worktree lease validator <path>: <err>` | `worktree-lease.py` could not be executed. | Check the helper path is executable. | validate-review-dir.py:888 |
| `active worktree lease validation failed: <detail>` | `worktree-lease.py check` rejected the lease. | See §7 and fix the underlying lease error. | validate-review-dir.py:893 |
| `pin.md has no mechanically readable changed-file list` | The changed-files block is missing or malformed. | Regenerate `pin.md` with `fetch-cl.sh`. | validate-review-dir.py:909 |

### 4.3 Unresolved Gerrit threads (`validate_unresolved`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `missing normalized Gerrit thread artifact: <path>` | `unresolved-threads.json` was never produced. | Run `extract-unresolved-comments.py <REVIEW_DIR>`. | validate-review-dir.py:917 |
| `unresolved-threads.json must contain an object` | Wrong top-level type. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:921 |
| `unresolved-threads.json requires summary, threads, and malformed` | A top-level key is missing. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:926 |
| `unresolved-threads.json summary has invalid <key>` | A summary counter is not a non-negative int. | Regenerate; do not hand-edit counts. | validate-review-dir.py:931 |
| `unresolved-threads.json summary has the wrong unresolved count` | `summary.unresolved_threads` disagrees with `threads`. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:933 |
| `unresolved-threads.json summary has the wrong malformed count` | Same for `malformed`. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:935 |
| `unresolved-threads.json total_threads is below unresolved_threads` | Impossible counts. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:939 |
| `unresolved thread entry is not an object` | An element of `threads` is a scalar. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:943 |
| `unresolved thread is missing <key>` | A thread record lacks a required key. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:947 |
| `thread <id> is present but not unresolved` | A resolved thread was listed as unresolved. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:949 |
| `duplicate normalized thread root: <id>` | Two entries share a root comment. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:952 |
| `thread <id> latest-comment state is inconsistent` | `latest_*` fields disagree with the comment list. | Regenerate with `extract-unresolved-comments.py`. | validate-review-dir.py:960 |

---

### 4.4 Trigger inventory (`validate_trigger_inventory`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `missing inventory.md or inventory/*.md artifacts` | No inventory artifact exists. | Produce `inventory.md` (or shards under `inventory/`) before running at `--phase collection`. | validate-review-dir.py:1644 |
| `<file>: Trigger inventory has the wrong columns` | Header of the `## Trigger inventory` table is wrong. | Copy the header from the inventory template in `references/templates.md`. | validate-review-dir.py:1660 |
| `<file>: invalid trigger scope ID '<id>'` | Scope ID does not match `T<n>` or `I<PREFIX>-T<n>`. | Rename the ID to `T12` or `IABC-T12` form. | validate-review-dir.py:1666, :169 |
| `duplicate trigger scope ID <id>: <a> and <b>` | Two inventory shards used the same trigger ID. | Prefix per-shard IDs (`I<SHARD>-T<n>`) so they are globally unique. | validate-review-dir.py:1669 |
| `<file>: <row> specialist token <t> must be '<lens> hard' or '<lens> absent'` | A specialist trigger cell used free text. | Write exactly `<Lens Name> hard` or `<Lens Name> absent`. | validate-review-dir.py:1692 |
| `<file>: <row> has invalid root-cause trigger '<v>'` | Root-cause trigger cell is not a recognized token. | Use the exact token set from the inventory template. | validate-review-dir.py:1697 |
| `<file>: <row> has no path:line trigger evidence` | A positive trigger cites nothing. | Add a `path/to/file.cc:123` citation in the evidence cell. | validate-review-dir.py:1703 |
| `<file>: <row> has no cited trigger-absence evidence` | An `absent` claim cites nothing. | Cite the scan/grep result that proves absence, as `path:line` or an artifact pointer. | validate-review-dir.py:1705 |
| `inventory artifacts have no ## Trigger inventory table` | The heading/table is missing entirely. | Add a `## Trigger inventory` section to `inventory.md`. | validate-review-dir.py:1709 |

### 4.5 `plan.md` roster, tiers, adaptive shards, specialist priors (`validate_plan`, `effective_plan_roster`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `plan.md has no roster table` | No roster table found. | Add the roster table from the plan template. | validate-review-dir.py:1195 |
| `plan.md roster table lacks a tier column` | Header has no `tier`. | Add the `tier` column to the roster header. | validate-review-dir.py:1198 |
| `plan row '<r>' has invalid tier '<t>'` | Tier is not in `MANIFEST_TIERS`. | Use `mechanical`, `standard`, `frontier`, or `inherit`. | validate-review-dir.py:1227 |
| `plan row '<r>' assigns mechanical tier to a discovery thread` | Discovery threads may not run mechanical. | Raise that row to `standard` or higher. | validate-review-dir.py:1230 |
| `plan row '<r>' runs below its <x> floor under a user tier-override` *(warning)* | Tier is below the floor but `directives.md` records an override. | No action; the override is honoured. | validate-review-dir.py:1237 |
| `plan row '<r>' tier '<t>' is below its <x> floor and directives.md records no tier-override` | `Mechanical Leads` / `Changed-Lines Polish` have a `standard` floor; everything else has a `frontier` floor. | Raise the tier, or record an explicit tier-override in `directives.md`. | validate-review-dir.py:1241, :176 |
| `plan row '<r>' has invalid status '<s>'` | Status cell is not a recognized value. | Use the status vocabulary from the plan template. | validate-review-dir.py:1298 |
| `plan.md omits roster entry: <name>` | A mandatory `ROSTER` thread has no row. | Add a row named exactly as in `ROSTER` (validate-review-dir.py:79), including `×` and `'`. | validate-review-dir.py:1302 |
| `plan.md invents or renames roster entry: <name>` | A row name is not in `ROSTER` / `GENERALIST_ROSTER`. | Rename it to the exact roster string; do not paraphrase. | validate-review-dir.py:1622 |
| `plan.md duplicates effective roster identity: <name>` | Two rows resolve to the same thread+shard. | Give each shard a distinct numeric suffix. | validate-review-dir.py:1628 |
| `plan.md mixes sharded and unsharded effective rows for <name>` | A thread has both `Foo` and `Foo 2` rows. | Either shard all of them or none of them. | validate-review-dir.py:1633, :1633 |
| `plan row '<r>' has a shard-like label with no shard number; it must not alias the unsharded work unit` | A label looks sharded but has no number. | Add the shard number, or drop the shard-like suffix. | validate-review-dir.py:2843 |
| `plan.md has duplicate spawn work unit <id>` | Two plan rows spawn the same work ID. | Give each row a unique work ID. | validate-review-dir.py:2864 |
| `plan row '<r>' is not applicable but positive <k> trigger rows exist: <ids>` | A row was marked N/A while its triggers fired. | Mark the row applicable and schedule it, or refute the listed triggers. | validate-review-dir.py:1260 |
| `plan row '<r>' omits <k> absence proof rows: <ids>` | An N/A row did not cite every absence proof. | Cite each listed trigger row in the plan row's proof cell. | validate-review-dir.py:1271 |
| `plan row '<r>' cites unknown trigger <id>` | Cited trigger ID is not in the inventory. | Correct the trigger ID. | validate-review-dir.py:1278 |
| `plan row '<r>' cites <id>, which does not prove trigger absence for <k>` | The cited row is not an absence proof. | Cite a row whose cell reads `<lens> absent`. | validate-review-dir.py:1284 |
| `plan row '<r>' cites <id>, which does not carry required '<k> absent' proof` | Wrong lens on the absence proof. | Cite the absence proof for the correct lens. | validate-review-dir.py:1291 |
| `cannot read adaptive topology index: <err>` | `topology.tsv` unreadable. | Run `build-review-indexes.py <REVIEW_DIR>`. | validate-review-dir.py:1317 |
| `adaptive graph plan requires spawned rows for <names>` | Graph-adaptive planning is on but generalist rows are missing. | Add the required generalist rows to `plan.md`. | validate-review-dir.py:1325 |
| `adaptive graph generalist <name> must be either one unsharded graph:all-inventory-edges row, one unsharded graph:none row for a zero-edge inventory, or only numbered exact-edge shards` | The generalist's scope cells mix shapes. | Pick one shape: a single `graph:all-inventory-edges` row, a single `graph:none` row, or numbered shards each citing exact edge IDs. | validate-review-dir.py:1354 |
| `adaptive graph generalist shard '<r>' must cite graph:<edge-id(s)>` | Shard scope is not an exact edge list. | Write `graph:E-1,E-2` in the scope cell. | validate-review-dir.py:1369 |
| `adaptive graph generalist <name> cites unknown edge(s): <ids>` | Edge IDs not in `topology.tsv`. | Correct the edge IDs, or rebuild indexes. | validate-review-dir.py:1381 |
| `adaptive graph generalist <name> omits edge(s): <ids>` | Shards do not cover every inventory edge. | Add the missing edges to a shard. | validate-review-dir.py:1386 |
| `adaptive graph generalist <name> duplicates edge(s): <ids>` | An edge appears in two shards. | Make the shard partition disjoint. | validate-review-dir.py:1391 |
| `adaptive graph generalist passes must use the same numbered edge partition` | The two generalists sharded differently. | Use an identical shard partition for both generalist passes. | validate-review-dir.py:1400 |
| `cannot read specialist prior index: <err>` | `specialist-priors.tsv` unreadable. | Run `build-review-indexes.py <REVIEW_DIR>`. | validate-review-dir.py:1411 |
| `specialist-priors.tsv contains a malformed assessment` | A row is not parseable. | Rebuild indexes; if it persists, fix the generalist ledger's assessment table. | validate-review-dir.py:1446 |
| `specialist prior duplicates <lens> for <assessor> graph:<scope>` | Two rows for the same lens/assessor/scope. | Remove the duplicate assessment row from the generalist ledger. | validate-review-dir.py:1456 |
| `specialist prior uses an unassigned graph scope for <lens>: graph:<scope>` | Assessment scope is outside the assessor's assigned shard. | Keep the lens scope within that shard; justify every excluded edge with cited counterevidence. | validate-review-dir.py:1477 |
| `specialist prior missing assessment for <lens> shard <n>: <assessor>` | An independent shard/lens assessment is absent. | Restore that generalist's assessment; another shard or the other pass cannot replace it. | validate-review-dir.py |
| `specialist prior for <lens> excludes assigned edges without cited counterevidence` | A narrowed scope silently drops edges. | Append an assessment amendment with cited low-risk justification for every excluded edge, or retain the edges and route the required work. | validate-review-dir.py |
| `specialist likelihood requires specialist:full for <lens>` | A `high` prior did not get a full specialist pass. | Add a plan row for that lens with scope `specialist:full`. | validate-review-dir.py:1516 |
| `specialist likelihood requires specialist:probe or specialist:full for <lens>` | A `medium` prior got nothing. | Add a plan row with scope `specialist:probe` (or `specialist:full`). | validate-review-dir.py:1523 |
| `positive <k> trigger <id> must cite exact graph scope` | The trigger row's scope is not `graph:<ids>`. | Put exact edge IDs in the trigger's graph-scope cell. | validate-review-dir.py:1536 |
| `positive <k> trigger <id> cites unknown graph edge(s): <ids>` | Bad edge IDs on a trigger. | Correct them against `topology.tsv`. | validate-review-dir.py:1546 |
| `positive <k> trigger <id> requires specialist:full coverage of graph:<ids>` | A hard trigger was not fully covered. | Add or widen a `specialist:full` plan row to cover those edges. | validate-review-dir.py:1553 |
| `cannot read adaptive candidate index: <err>` | `candidates.tsv` unreadable. | Run `build-review-indexes.py <REVIEW_DIR>`. | validate-review-dir.py:1568 |
| `adaptive topology omits candidate edge membership: <ids>` | A candidate is not attached to any edge. | Rebuild indexes; if it persists, add the candidate's edge membership to the topology table. | validate-review-dir.py:1579 |
| `adaptive topology cites unknown candidate(s): <ids>` | Topology references non-existent candidates. | Rebuild indexes after fixing the ledger row IDs. | validate-review-dir.py:1584 |
| `adaptive targeted row '<r>' scope must cite graph:<edge-id(s)>` | Targeted round-two row has no edge scope. | Write `graph:E-1,E-2` in its scope cell. | validate-review-dir.py:1596 |
| `adaptive targeted row '<r>' cites unknown graph edge(s): <ids>` | Bad edge IDs. | Correct them against `topology.tsv`. | validate-review-dir.py:1603 |
| `adaptive specialist row '<r>' scope must declare specialist:full or specialist:probe` | Specialist row scope is free text. | Use exactly `specialist:full` or `specialist:probe`. | validate-review-dir.py:1611 |

### 4.5b Specialist probe execution (`validate_specialist_probe_execution`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `<file>: specialist probe ledger is noncanonical; expected <path>` | Probe artifact is not at the canonical ledger path. | Move the probe output to the expected `ledger/<ID>.md` path and re-seal. | validate-review-dir.py:1027 |
| `<file>: specialist probe requires exactly one Specialist probe outcome table` | Zero or several outcome tables. | Keep exactly one `## Specialist probe outcome` table. | validate-review-dir.py:1045 |
| `<file>: Specialist probe outcome must have the required columns and exactly one row` | Wrong shape. | Copy the probe-outcome table from `references/templates.md`. | validate-review-dir.py:1055 |
| `<file>: probe outcome names the wrong specialist lens` | Lens cell does not match the plan row. | Set the lens to the exact `SPECIALIST_LENSES` name assigned in `plan.md`. | validate-review-dir.py:1062 |
| `<file>: probe outcome graph scope differs from plan` | Scope drifted from the assignment. | Copy the assigned graph scope from `plan.md` verbatim. | validate-review-dir.py:1072 |
| `<file>: probe result must be clean or escalate` | Free-text result. | Write exactly `clean` or `escalate`. | validate-review-dir.py:1075 |
| `<file>: probe outcome lacks cited evidence` | No `path:line` in the evidence cell. | Add a `path/to/file.cc:123` citation. | validate-review-dir.py:1079 |
| `<file>: clean probe has a candidate or open graph obligation` | A `clean` probe still raised work. | Change the result to `escalate`, or remove the candidate/obligation. | validate-review-dir.py:1096 |
| `<file>: clean probe must have no remaining scope` | `remaining_scope` is set on a clean probe. | Set `remaining_scope` to `-` for clean probes. | validate-review-dir.py:1100 |
| `<file>: escalated probe must retain specialist:full graph scope` | Escalation narrowed the scope. | Keep the full assigned `specialist:full` scope on the escalation. | validate-review-dir.py:1111 |
| `cannot read probe orchestration: <err>` | `orchestration.tsv` unreadable during the probe check. | Fix `orchestration.tsv` parse errors first (§4.7). | validate-review-dir.py:1125 |
| `<file>: escalated probe lacks a later complete same-work-ID specialist:full continuation` | An escalation was never followed up. | Seal and complete a later attempt of the same work ID at `specialist:full`. | validate-review-dir.py:1181 |

---

### 4.6 `input-manifest.tsv` (`validate_input_manifest`)

Row numbers in these messages are 1-based **file** line numbers, so
`input-manifest.tsv:2` is the first data row (line 1 is the header).

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `missing required worker input manifest: <path>` | No `input-manifest.tsv`. | Seal at least one work unit: `seal-work-unit.py <REVIEW_DIR> --phase ... --work-id ... --attempt 1 --tier ... --brief ... --artifact ...`. | validate-review-dir.py:2396 |
| `input-manifest.tsv has wrong columns or order` | Header does not equal `INPUT_MANIFEST_COLUMNS`. | Restore the header to `work_id attempt phase brief input_path role bytes sha256` (tab-separated). Never hand-write this file; let `seal-work-unit.py` own it. | validate-review-dir.py:2402, :225 |
| `cannot parse input-manifest.tsv: <err>` | Not valid TSV. | Restore from the last good state and re-seal; do not hand-edit. | validate-review-dir.py:2406 |
| `input-manifest.tsv:<N>: invalid work_id` | Empty work ID or one containing tab/CR/LF. | Re-seal with a clean `--work-id`. | validate-review-dir.py:2428 |
| `input-manifest.tsv:<N>: invalid attempt '<a>'` | Attempt is not a positive integer. | Re-seal with `--attempt <positive int>`. | validate-review-dir.py:2435 |
| `input-manifest.tsv:<N>: blank phase` | Phase column empty. | Re-seal with `--phase <name>`. | validate-review-dir.py:2441 |
| `input-manifest.tsv:<N>: invalid role '<r>'` | Role not in `INPUT_MANIFEST_ROLES`. | Use one of `brief`, `control`, `reference`, `assigned`, `candidate-packet`, `card`, `frame`, `section`, `prestate`. | validate-review-dir.py:2443, :229 |
| `input-manifest.tsv:<N>: brief is not absolute` | Relative brief path. | Re-seal passing an absolute `--brief`. | validate-review-dir.py:2449 |
| `input-manifest.tsv:<N>: input_path is not absolute` | Relative input path. | Re-seal passing `--input ROLE=/absolute/path`. | validate-review-dir.py:2451 |
| `input-manifest.tsv:<N>: missing input <path>` | A sealed input file was deleted or moved. | Restore the file at the recorded path. Sealed inputs are immutable evidence; do not re-point the manifest. | validate-review-dir.py:2454 |
| `input-manifest.tsv:<N>: invalid bytes value` | `bytes` column is not an integer. | Re-seal the work unit; do not hand-edit the column. | validate-review-dir.py:2463 |
| **`input-manifest.tsv:<N>: byte count mismatch for <path>: <recorded> != <actual>`** | The file changed size after it was sealed. For append-only artifacts this means it was rewritten, not appended. | Restore the exact sealed content, **or** seal a new attempt (`--attempt <n+1>`) that records the new bytes. Never edit the `bytes` column to match. | validate-review-dir.py:2494 |
| `input-manifest.tsv:<N>: sha256 mismatch for <path>` | Content changed at the same length. | Restore the sealed content, or seal a new attempt. Never edit the `sha256` column. | validate-review-dir.py:2504 |
| `input-manifest.tsv:<N>: prestate prefix <n> exceeds current size of <path>` | A `prestate` input got *shorter* than its recorded prefix — the file was truncated. | Restore the file; `prestate` inputs may only grow. | validate-review-dir.py:2469 |
| **`input-manifest.tsv:<N>: prestate prefix hash mismatch for <path> — prior content was rewritten, not appended`** | A `prestate` input's first `<n>` bytes changed. The append-only contract is broken. | Restore the original prefix byte-for-byte and re-apply your change as an **append**. If the rewrite was intentional, seal a new attempt with a fresh `prestate` row instead of mutating history. | validate-review-dir.py:2474 |
| `work unit <w> attempt <a> has a brief but no input-manifest rows` | Brief exists, seal never ran. | Run `seal-work-unit.py` for that work ID/attempt. | validate-review-dir.py:2536 |
| `input manifest work <w> attempt <a> has no orchestration.tsv attempt` | `input-manifest.tsv` and `orchestration.tsv` disagree. | Re-seal; both files are written atomically by `seal-work-unit.py`, so a split means one was hand-edited. | validate-review-dir.py:2541 |
| `input manifest work <w> names multiple briefs` | One work ID sealed against two brief paths. | Give each attempt its own work ID, or reuse the single canonical brief. | validate-review-dir.py:2548 |
| `input manifest work <w> names multiple phases` | One work ID sealed under two phases. | Re-seal with a consistent `--phase`. | validate-review-dir.py:2550 |
| `input manifest work <w> attempt <a> names brief <x> but orchestration.tsv records <y>` | Brief paths diverged between the two files. | Re-seal the attempt; do not patch either TSV. | validate-review-dir.py:2554 |
| `input manifest work <w> card <c> exceeds profile evidence-card budget (<x> > <y>)` | A `card` input is too large. | Split the evidence card, or raise `evidence_card_budget_bytes` in the profile only if genuinely justified. | validate-review-dir.py:2572 |
| `input manifest work <w> exceeds its worker-input budget (<x> > <y> bytes...)` | Total sealed inputs exceed the tier budget. | Shard the work unit, or drop inputs. See also seal-time `work unit inputs exceed budget`. | validate-review-dir.py:2591 |
| `input manifest work <w> candidate packets exceed profile budget (<x> > <y> bytes)` | `candidate-packet` inputs too large in aggregate. | Split the packet across more work units. | validate-review-dir.py:2599 |
| `input manifest work <w> attempt <a> has <n> input-manifest self rows, expected 1` | Zero or several `role=brief` rows. | Re-seal the attempt; exactly one self row is written per seal. | validate-review-dir.py:2604 |
| `generated analytical brief <path> has 0 input-manifest self rows` | A brief under `briefs/` was never sealed. | Run `seal-work-unit.py ... --brief <path> ...`. | validate-review-dir.py:2621 |
| `input-manifest self row references unknown brief <path>` | Self row points at a nonexistent brief. | Restore the brief file, or re-seal. | validate-review-dir.py:2625 |
| **`generated analytical brief <B> names input <X> in Inputs/Procedure but input-manifest.tsv omits it`** | The brief's `Inputs:`/`Procedure:` prose mentions a file that was never passed as `--input` at seal time. The validator parses those sections for paths. | Re-seal the attempt with `--input <role>=<X>` for every file the brief names, **or** remove the mention from the brief's Inputs/Procedure sections. Mentioning a file you did not seal is the error; the file list and the prose must agree exactly. | validate-review-dir.py:2642, :1889 |
| `no generated briefs/*.md artifacts found` | `briefs/` is empty at `--phase collection` or later. | Generate briefs with `build-phase-brief.py` before running the gate. | validate-review-dir.py:2377 |
| `<brief>: generated brief lacks <k> contract` | A brief is missing one of the `BRIEF_REQUIREMENTS` clauses: `directives` (must mention `directives.md`), `pin/revision`, `authority boundary` (must say "authority boundary" or "untrusted"), `append/retry` (must say "append-only" or "amendment"), `partial return` (must say "partial"). | Add the missing clause to the brief; the common header template in `references/phase-briefs.md` already contains all five. | validate-review-dir.py:2386, :233 |
| `procedural repair chain at <path>:<line> has a cycle or violates strict attempt ordering through <id>` | Repair supersession chain loops or goes backwards in attempt number. | Make each repair target a strictly earlier attempt; break the cycle. | validate-review-dir.py:2313 |
| `procedural target <path>:<line> is claimed by <n> valid repairs` | Two repairs supersede the same row. | Keep exactly one repair per superseded target. | validate-review-dir.py:2337 |

### 4.7 `orchestration.tsv` (`validate_manifest`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `missing required orchestration manifest: <path>` | No `orchestration.tsv`. | Seal a work unit with `seal-work-unit.py`. | validate-review-dir.py:2658 |
| `orchestration.tsv has wrong columns or order` | Header does not equal `MANIFEST_COLUMNS`. | Restore the header to `phase work_id attempt state tier task_id brief artifact remaining_scope depends_on`. | validate-review-dir.py:2664, :170 |
| `cannot parse orchestration.tsv: <err>` | Not valid TSV. | Restore and re-seal; do not hand-edit. | validate-review-dir.py:2668 |
| `orchestration.tsv:<N>: duplicate work_id/attempt <key>` | Two rows share `(work_id, attempt)`. | Delete the duplicate row, or bump one to the next attempt number. | validate-review-dir.py:2678 |
| `orchestration.tsv:<N>: invalid attempt '<a>'` | Attempt is not a positive integer. | Set a positive integer attempt. | validate-review-dir.py:2685 |
| `orchestration.tsv:<N>: invalid state '<s>'` | State is not in `MANIFEST_STATES`. | Use exactly one of `queued`, `running`, `partial`, `retryable`, `needs-repair`, `complete`, `terminated`. | validate-review-dir.py:2690, :221 |
| `orchestration.tsv:<N>: invalid tier '<t>'` | Tier is not in `MANIFEST_TIERS`. | Use `mechanical`, `standard`, `frontier`, or `inherit`. | validate-review-dir.py:2692, :174 |
| `orchestration.tsv:<N>: <state> requires remaining_scope` | `partial`, `retryable`, `needs-repair` or `terminated` rows must state what is left. | Fill `remaining_scope` with the exact unfinished scope (not `-`). | validate-review-dir.py:2696 |
| `orchestration.tsv:<N>: <column> is not absolute` | `brief` or `artifact` is relative. | Write absolute paths. | validate-review-dir.py:2700 |
| `work unit <w> has missing/empty brief <path>` | Brief was deleted or is zero bytes. | Restore the brief; sealed briefs are read-only by design. | validate-review-dir.py:2704 |
| `completed analytical unit <w> records no artifact` | `complete` row has `artifact` = `-`. | Set `artifact` to the produced `ledger/<ID>.md` path. | validate-review-dir.py:2708 |
| `completed unit <w> has missing/empty artifact <path>` | The artifact does not exist or is empty. | Write the artifact, or move the row back to `partial`/`retryable`. | validate-review-dir.py:2714 |
| `canonical artifact <path> has concurrent writers <a> and <b>` | Two work units claim the same artifact path. | Give each work unit its own artifact path. | validate-review-dir.py:2719 |
| `manifest attempts for <w> are not unique and increasing` | Attempt numbers skip backwards or repeat. | Renumber attempts 1, 2, 3… in order. | validate-review-dir.py:2725 |
| **`work unit <W> is a frontier-contract kind but an attempt recorded tier '<t>'`** | Work IDs matching `V<n>`, `VTER`, `RC<n>`, `CH*`, `VPLAN*`, `RCPLAN*`, `PLAN`, `PR` must run at `frontier`. | Re-seal that attempt with `--tier frontier`, or record an explicit tier-override in `directives.md` (which downgrades this to a warning). | validate-review-dir.py:2737, :2727 |
| `work unit <W> is a frontier-contract kind but an attempt recorded tier '<t>' under a user tier-override` *(warning)* | Same condition, but `directives.md` records an override. | No action required. | validate-review-dir.py:2739 |
| `work unit <w> continuation dropped from tier '<a>' to '<b>'` | A later attempt ran at a lower tier than the first. | Re-seal the continuation at the original tier or higher, or record a tier-override. | validate-review-dir.py:2746 |
| `work unit <w> attempt <a> does not depend on a prior attempt of the same unit` | A continuation has no `depends_on` back-link. | Re-seal with `--depends-on <work_id>:<prior attempt>`. | validate-review-dir.py:2765 |
| `work unit <w> attempt <a> reuses attempt <b>'s brief; continuations need an attempt-specific brief with the explicit remainder` | The retry pointed at the first attempt's brief. | Write a new brief for the continuation stating the remaining scope, then seal with that brief. | validate-review-dir.py:2777 |
| `work unit <w> has unknown dependency <d>` | `depends_on` names a work unit that does not exist. | Correct the dependency ID. | validate-review-dir.py:2795 |
| `work unit <w> is <state> while dependency <d> is <state>` | A unit advanced past an unfinished dependency. | Complete the dependency first, or move the dependent back. | validate-review-dir.py:2818 |
| `work unit <w> is non-terminal at final validation: <state>` | At `--phase final`, everything must be `complete` or `terminated`. | Finish the unit, or terminate it with a recorded `remaining_scope` and a matching `collection.md` Gaps row. | validate-review-dir.py:2824 |
| `an interrupted work-unit seal transaction needs recovery; rerun the original exact seal-work-unit.py command before continuing (an identical recovered attempt returns success)` | `.work-unit-seal-transaction.json` is present: a seal was interrupted mid-commit. | Re-run the **exact** original `seal-work-unit.py` command. Do not increment the attempt; an identical seal replays the journal and prints `already sealed ...`. | validate-review-dir.py:5229 |
| `per-file floor missing ledger/ORC row for <path>` | A file changed by the CL has no `ledger/ORC*.md` coverage row. | Add an ORC ledger row covering that file, or explain it under an existing one. | validate-review-dir.py:5260 |

---

### 4.8 `collection.md` coverage (`validate_collection_coverage`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `collection.md Thread audit table must have exactly the ordered columns thread \| expected artifact \| matrix \| anomaly-to-candidate \| append/amendments \| verdict` | Audit table header is wrong. | Copy that exact header row. | validate-review-dir.py:2900 |
| `collection.md Thread audit has duplicate rows for '<t>'` | Two audit rows for one thread. | Delete the duplicate. | validate-review-dir.py:2908 |
| `collection.md Thread audit verdict for '<t>' must be 'pass' or 'gap: ...', got '<v>'` | Free-text verdict. | Write `pass`, or `gap: <what is missing>`. | validate-review-dir.py:2915 |
| `collection.md Thread audit row for '<t>' is verdict pass but its cells do not read complete/complete/valid` | A `pass` row has non-complete cells. | Set matrix/anomaly-to-candidate/append cells to `complete`/`complete`/`valid`, or change the verdict to `gap: ...`. | validate-review-dir.py:2928 |
| `collection.md lacks a Thread audit table` | Table missing. | Add the `## Thread audit` table. | validate-review-dir.py:2938 |
| `collection.md lacks an Audit result section` | Section missing. | Add the `## Audit result` section. | validate-review-dir.py:2940 |
| `collection.md Audit result section must contain exactly one value line, the normalized token 'complete'; finish repairs or record gaps as terminated — unreviewed before this gate` | The section has prose, or more than one line, or a token other than `complete`. | Replace the section body with the single word `complete`. If work is genuinely missing, terminate those units in `orchestration.tsv` and add matching Gaps rows first. | validate-review-dir.py:2947 |
| `spawned work unit '<w>' has no ledger/<w>.md artifact` | Plan spawned it; no ledger file. | Write `ledger/<w>.md`, or drop the spawn row. | validate-review-dir.py:2959 |
| `spawned work unit '<w>' has no orchestration.tsv attempt` | Never sealed. | Seal it with `seal-work-unit.py`. | validate-review-dir.py:2963 |
| `spawned work unit '<w>' has no terminal orchestration attempt (complete/terminated)` | Still in flight. | Complete or terminate the unit. | validate-review-dir.py:2968 |
| `work unit <w>'s completed attempt artifact '<x>' is not ledger/<w>.md` | Artifact path is non-canonical. | Re-seal with `--artifact <REVIEW_DIR>/ledger/<w>.md`. | validate-review-dir.py:2975 |
| `collection.md Thread audit has no row for spawned work unit '<w>'` | Audit table missed a spawned unit. | Add an audit row for it. | validate-review-dir.py:2981 |
| `collection.md Thread audit row for '<t>' has an empty verdict` | Blank verdict cell. | Fill in `pass` or `gap: ...`. | validate-review-dir.py:2986 |
| `collection.md Thread audit row for '<t>' names expected artifact '<x>', not <y>` | Audit row points at the wrong file. | Correct the expected-artifact cell to the canonical ledger path. | validate-review-dir.py:2991 |
| `work unit <w> attempt ran at <t>, below its planned <p> tier, under a user tier-override` *(warning)* | Downgrade is covered by an override. | No action. | validate-review-dir.py:3002 |
| `work unit <w> attempt ran at <t>, below its planned <p> tier, with no tier-override in directives.md` | Execution tier is lower than the plan's. | Re-run the unit at the planned tier, or record an explicit tier-override in `directives.md`. | validate-review-dir.py:3007 |
| `collection.md Thread audit records a gap for '<t>' with no matching Gaps row` | `gap:` verdict without a Gaps entry. | Add the Gaps row. | validate-review-dir.py:3015 |
| `collection.md Thread audit row '<t>' is verdict pass but a Gaps row exists for it` | Contradiction. | Delete the Gaps row, or change the verdict to `gap: ...`. | validate-review-dir.py:3019 |
| `collection.md Gaps row '<g>' matches neither a gap-verdict audit row nor an unreviewed plan row` | Orphan Gaps row. | Delete it, or add the matching audit/plan row. | validate-review-dir.py:3028 |
| `collection.md Audit result is complete while gap unit '<w>' is not terminated in orchestration.tsv (state '<s>')` | A gap's work unit is still open. | Set that unit's state to `terminated` with the exact `remaining_scope`. | validate-review-dir.py:3036 |
| `gap unit '<w>' scope '<a>' does not equal its terminated attempt's remaining_scope '<b>'` | Gaps row text and manifest disagree. | Make the Gaps row scope byte-identical to `remaining_scope`. | validate-review-dir.py:3045 |
| `unreviewed plan row '<r>' has no terminated orchestration attempt for <w> (state '<s>')` | Plan says unreviewed; manifest disagrees. | Terminate the attempt, or change the plan status. | validate-review-dir.py:3052 |
| `unreviewed plan row '<r>' has no matching collection Gaps row for <w>` | Unreviewed row with no gap recorded. | Add the Gaps row in `collection.md`. | validate-review-dir.py:3057 |

### 4.9 TER / VTER gate (`validate_ter_gate`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `<file>: sentinel row coexists with other class rows in this shard` | The no-classes sentinel is mixed with real `TC` rows. | Delete the sentinel row. | validate-review-dir.py:3095 |
| `<file>: no-classes sentinel row must have member count 0` | Sentinel has a nonzero count. | Set the member count to `0`. | validate-review-dir.py:3101 |
| `<file>: no-classes sentinel row must not name files` | Sentinel lists files. | Empty the files cell. | validate-review-dir.py:3105 |
| `<file>: no-classes sentinel row needs concrete scan evidence in its proof cell, not a placeholder` | Proof cell is boilerplate. | Cite the actual scan you ran (command plus result, or `path:line`). | validate-review-dir.py:3109 |
| `<file>: invalid transformation class ID '<id>'` | ID is not `TC<n>`. | Rename to `TC1`, `TC2`, … | validate-review-dir.py:3116 |
| `<file>: duplicate class <id>` | Same `TC` twice. | Merge or renumber. | validate-review-dir.py:3121 |
| `<file>: class <id> lists duplicate files` | Repeated path in the files cell. | De-duplicate the list. | validate-review-dir.py:3127 |
| `<file>: class <id> lists no files; the files cell must be an explicit path list` | Empty or hand-wavy files cell. | List every member path explicitly. | validate-review-dir.py:3132 |
| `<file>: class <id> member count '<n>' is missing or below its file count` | Count is absent or too small. | Set the count to at least the number of listed files. | validate-review-dir.py:3137 |
| `TER is spawned but no ledger/TER*.md exists` | TER thread planned, nothing produced. | Write the TER ledger artifact, or drop the TER spawn row. | validate-review-dir.py:3154 |
| `<file> lacks a Transformation classes table` | Missing table. | Add the `## Transformation classes` table. | validate-review-dir.py:3157 |
| `<file> lacks a Residue section` | Missing section. | Add the `## Residue` section. | validate-review-dir.py:3160 |
| `<file>: Transformation classes table has neither a valid TC class nor the explicit no-classes sentinel row` | Table is empty. | Add `TC` rows, or the explicit no-classes sentinel row. | validate-review-dir.py:3162 |
| `a no-classes sentinel row coexists with real transformation classes` | Sentinel in one shard, classes in another. | Delete the sentinel. | validate-review-dir.py:3166 |
| `class <id> lists <f> but has no clean/mixed membership row for it` | A listed file has no membership verdict. | Add a membership row for that file. | validate-review-dir.py:3174 |
| `class <id> has <n> membership rows for <f>` | Duplicate membership rows. | Keep exactly one per (class, file). | validate-review-dir.py:3178 |
| `membership row cites <f> which class <id> does not list` | Membership row outside the class's file list. | Add the file to the class, or delete the membership row. | validate-review-dir.py:3183 |
| `membership row cites unknown class <id>` | Membership row references a nonexistent `TC`. | Correct the class ID. | validate-review-dir.py:3187 |
| `TER produced transformation classes but verification/VTER.md is missing` | The gate artifact was never written. | Run the VTER gate and write `verification/VTER.md`. | validate-review-dir.py:3193 |
| `VTER.md gate table must have exactly the ordered columns id \| class \| verdict \| evidence` | Wrong header. | Use exactly those four columns in that order. | validate-review-dir.py:3203 |
| `VTER.md row ID '<id>' is not VTER-<n>` | Bad row ID. | Rename to `VTER-1`, `VTER-2`, … | validate-review-dir.py:3210 |
| `VTER.md duplicates row ID <id>` | Two rows share an ID. | Renumber. | validate-review-dir.py:3212 |
| `VTER.md has duplicate verdict for <TC>` | Two verdicts for one class. | Keep exactly one verdict per class. | validate-review-dir.py:3218 |
| `VTER.md verdict '<v>' for <TC> is not PROVEN/REJECTED/UNPROVEN` | Bad verdict token. | Use `PROVEN`, `REJECTED`, or `UNPROVEN`. | validate-review-dir.py:3222, :219 |
| `VTER.md <v> verdict for <TC> has no path:line citation — the gate accepts no evidence-exception` | Evidence cell has no citation. | Add a real `path/to/file.cc:123`. `evidence-exception:` is **not** accepted here, unlike other gates. | validate-review-dir.py:3227 |
| `VTER.md verdict targets unknown transformation class <TC>` | Verdict for a class that does not exist. | Correct the class ID. | validate-review-dir.py:3232 |
| `VTER.md lacks the id \| class \| verdict \| evidence gate table` | Table missing. | Add it. | validate-review-dir.py:3236 |
| `transformation class <TC> has no VTER gate verdict` | A class was never gated. | Add a `VTER-<n>` row for it. | validate-review-dir.py:3239 |
| `verification/VTER.md exists without a VTER orchestration work unit — the gate has no execution provenance` | Artifact written without sealing. | Seal a `VTER` work unit with `seal-work-unit.py --work-id VTER --tier frontier --artifact <...>/verification/VTER.md`. | validate-review-dir.py:3262 |
| `VTER work unit is not complete` | State is not `complete`. | Finish the unit and set its state. | validate-review-dir.py:3267 |
| `VTER work unit recorded tier '<t>'; the gate is frontier-only` | VTER ran below frontier. | Re-seal at `--tier frontier`. | validate-review-dir.py:3269 |
| `VTER work unit's artifact is not verification/VTER.md` | Wrong artifact path. | Re-seal with the canonical artifact path. | validate-review-dir.py:3275 |
| `VTER work unit has no brief` | Brief column is empty. | Re-seal with `--brief`. | validate-review-dir.py:3278 |
| `VTER work unit does not depend on the gate-brief builder (VTERB)` | Missing dependency. | Re-seal VTER with `--depends-on VTERB`. | validate-review-dir.py:3283 |
| `verification/VTER.md exists without a VTERB gate-brief builder work unit` | No builder unit. | Seal a `VTERB` unit that produces the VTER brief. | validate-review-dir.py:3301 |
| `VTERB work unit is not complete` | Builder unfinished. | Complete it. | validate-review-dir.py:3306 |
| `VTERB does not depend on spawned TER work unit <w>; the builder must consume every TER shard` | Builder missed a shard. | Add every TER shard to VTERB's `--depends-on`. | validate-review-dir.py:3312 |
| `plan row '<r>' is residue-scoped to <TC> without a PROVEN VTER gate verdict` | Residue work scheduled on an unproven class. | Get a `PROVEN` VTER verdict for that class first, or rescope the plan row. | validate-review-dir.py:3325 |
| `residue-scoped work unit <w> has no orchestration attempt depending on VTER or the round-two Planner` | Residue unit not wired to the gate. | Re-seal with `--depends-on VTER` (or the round-two planner unit). | validate-review-dir.py:3355 |
| `plan row '<r>' has a malformed residue scope '<s>'; the required form is 'residue(TC<ids>): <exact scope>'` | Scope string does not match `RESIDUE_SCOPE`. | Write it as `residue(TC1, TC2): <exact scope text>`. | validate-review-dir.py:3360, :220 |

---

### 4.10 Ledger, candidate descriptors, verdicts (`ledger_data`, `validate_candidate_descriptors`, `validate_verdicts`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `no ledger/*.md artifacts found` | `ledger/` is empty. | Produce at least one ledger artifact before running at `--phase collection`. | validate-review-dir.py:3379 |
| `duplicate row ID <id>: <a> and <b>` | Two ledger files define the same row ID. | Prefix row IDs per thread (`ROSTER_PREFIX`, validate-review-dir.py:113) so they are globally unique. | validate-review-dir.py:3373, :3420 |
| `<file> lacks exact Prior-feedback rows/Candidate rows headings` | Required headings missing. | Add both `## Prior-feedback rows` and `## Candidate rows` headings verbatim. | validate-review-dir.py:3385 |
| `<file> lacks exact Candidate rows heading` | Missing `## Candidate rows`. | Add it verbatim. | validate-review-dir.py:3388 |
| `<file> lacks exact Compliance matrix/Candidate rows headings` | Missing headings. | Add both verbatim. | validate-review-dir.py:3390 |
| `<file>: compliance matrix row <r> has a blank answer/evidence` | Empty cell. | Fill both cells. | validate-review-dir.py:3397 |
| `<file>: compliance matrix row <r> is a citation-free PASS` | `PASS` with no `path:line`. | Add a real citation, or downgrade the answer. | validate-review-dir.py:3399 |
| `<file>: compliance matrix row <r> has N/A without a reason` | Bare `N/A`. | Write `N/A — <specific reason>`. | validate-review-dir.py:3401 |
| `<file>: invalid prior-feedback row ID '<id>'` | ID does not match `ROW_ID`. | Use `<PREFIX>-<n>` or `R<n>-RC<n>-<n>`. | validate-review-dir.py:3406, :36 |
| `<file>: invalid candidate row ID '<id>'` | Same, for candidates. | Use `<PREFIX>-<n>` form. | validate-review-dir.py:3413 |
| `missing required artifact: collection.md` | `collection.md` absent at this phase. | Write `collection.md`. | validate-review-dir.py:3447 |
| `<file>: Candidate descriptors has wrong columns` | Header mismatch against `DESCRIPTOR_COLUMNS`. | Use exactly: `candidate`, `classes`, `obligations`, `base / interface`, `invariant owner`, `violated invariant`, `state / transition`, `proposed fix layer`, `related symbols`. | validate-review-dir.py:3498, :206 |
| `candidate <c> has duplicate descriptor rows in <a> and <b>` | Two ledgers describe one candidate. | Keep the descriptor in the owning ledger only. | validate-review-dir.py:3503 |
| `candidate <c> has no Candidate descriptors row` | Missing descriptor. | Add a descriptor row for that candidate. | validate-review-dir.py:3512 |
| `<file>: candidate <c> has invalid classes <x>` | Class not in `CLASS_OBLIGATIONS`. | Use `general`, `contract`, `async-lifetime`, `style-convention`, `state-protocol`, or `platform`. | validate-review-dir.py:3520, :189 |
| `<file>: candidate <c> has invalid obligations <x>` | Obligation not in `OBLIGATIONS`. | Use a value from the obligations list in §1. | validate-review-dir.py:3525, :179 |
| `<file>: candidate <c> lacks class-required obligations <x>` | The declared class implies obligations you did not list. | Add the listed obligations (e.g. `contract` requires `base-contract`, `caller-reachability`, `callee/backend-implementation`). | validate-review-dir.py:3535, :189 |
| `<file>: candidate <c> has unresolved descriptor '<cell>'; use 'unknown — reason' if necessary` | A descriptor cell is `?`, `TBD`, or empty. | Write the real value, or `unknown — <specific reason>`. | validate-review-dir.py:3544 |
| `<file>: Candidate descriptors references non-candidate <id>` | Descriptor for a row that is not a candidate. | Remove the row, or promote the ID to a candidate. | validate-review-dir.py:3550 |
| `<file>: worker-artifact validation failed: <detail>` | `validate-worker-artifact.py` rejected this ledger. | Look the inner message up in §10 and fix it there. | validate-review-dir.py:3576 |
| `<file>: invalid verdict '<v>' for <c>` | Verdict token unknown. | Use `CONFIRMED`, `REFUTED`, or `UNPROVEN`. | validate-review-dir.py:3591 |
| `<file>: <v> verdict for <c> has no path:line citation or evidence-exception` | Uncited verdict. | Add a `path:line` citation, or an explicit `evidence-exception: <reason>`. | validate-review-dir.py:3595, :177 |
| `<file>: verdict for <c> has no path:line detectable by validator` *(warning)* | Citation present but not in the recognized form. | Optional: reformat the citation as bare `path/to/file.cc:123`. | validate-review-dir.py:3599 |
| `candidate <c> has no verdict and no verdict-covered merge survivor` | Candidate never adjudicated. | Add a verdict row, or merge it into a verdict-owning survivor. | validate-review-dir.py:3614 |
| `candidate <c> has <n> verdict rows` | Zero or several verdicts. | Keep exactly one verdict per candidate. | validate-review-dir.py:3616 |
| `verdict references unknown/non-candidate row <id>` | Verdict targets a nonexistent row. | Correct the row ID. | validate-review-dir.py:3619 |
| `<file> references non-canonical reopened row <id>` | Reference to a superseded row. | Point at the canonical row instead. | validate-review-dir.py:3625 |

### 4.11 Root families and consistency audit (`validate_affinity`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `<file>: Root families has wrong columns` | Header mismatch. | Copy the `## Root families` header from `references/templates.md`. | validate-review-dir.py:3669 |
| `<file>: invalid root family '<id>'` | ID does not match `RF\d{3,}`. | Rename to `RF001`, `RF002`, … | validate-review-dir.py:3674, :178 |
| `<file>: duplicate root family <id>` | Two rows for one family. | Merge them. | validate-review-dir.py:3677 |
| `<file>: root family <id> has no members` | Empty members cell. | List the member row IDs. | validate-review-dir.py:3681 |
| `<file>: root family <id> has unknown member <r>` | Member ID does not exist. | Correct the row ID. | validate-review-dir.py:3684 |
| `<file>: row <r> belongs to both <a> and <b>` | A row is in two families. | Assign it to exactly one family. | validate-review-dir.py:3690 |
| `<file>: root family <id> has blank <column>` | A required family cell is empty. | Fill it in. | validate-review-dir.py:3700 |
| `<file>: Consistency audit has wrong columns` | Header mismatch. | Copy the `## Consistency audit` header from the template. | validate-review-dir.py:3708 |
| `<file>: unknown consistency audit check '<c>'` | Check name is not in `CONSISTENCY_CHECKS`. | Use one of the six names listed in §1, verbatim. | validate-review-dir.py:3715, :211 |
| `<file>: consistency audit check '<c>' has no result` | Blank result cell. | Record the result. | validate-review-dir.py:3719 |
| `<file>: consistency audit check '<c>' has no code/artifact evidence or evidence-exception` | Uncited check. | Add a `path:line` or a review-relative artifact pointer (`ledger/X.md:/anchor`), or an `evidence-exception: <reason>`. | validate-review-dir.py:3727, :58 |
| `<file>: missing ## Root families table` | Section absent. | Add it. | validate-review-dir.py:3732 |
| `<file>: missing ## Consistency audit table` | Section absent. | Add it. | validate-review-dir.py:3734 |
| `<file>: consistency check '<c>' occurs <n> times` | Duplicate check rows. | Keep exactly one row per check. | validate-review-dir.py:3737 |
| `<file>: surviving candidate/verdict <c>/<v> is not fully assigned to a root family` | A survivor has no family. | Assign it to a root family. | validate-review-dir.py:3745 |
| `<file>: candidate/verdict <c>/<v> split across <a>/<b>` | Survivor claimed by two families. | Assign to one family. | validate-review-dir.py:3750 |

### 4.12 Root-cause trigger accounting (`validate_root_cause_trigger_accounting`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `<file>: Trigger accounting has the wrong columns` | Header mismatch. | Copy the `## Trigger accounting` header from the template. | validate-review-dir.py:1735 |
| `<file>: trigger <a>/<b> uses root family '<x>', expected '<y>'` | Accounting disagrees with the authoritative affinity table. | Set the root family to the value from the affinity artifact. | validate-review-dir.py:1758 |
| `<file>: scheduled root family <id> has invalid RC batch '<b>'` | RC batch cell is malformed. | Write the batch as `RC<n>`. | validate-review-dir.py:1764 |
| `<file>: missing ## Trigger accounting table` | Section absent. | Add it. | validate-review-dir.py:1779 |
| `root-cause trigger scope <s> has <n> accounting rows` | Zero or duplicate accounting rows. | Keep exactly one accounting row per root-cause scope. | validate-review-dir.py:1782 |
| `root-cause-required scope <s> is not scheduled to an RC batch` | Required scope never scheduled. | Schedule it into an `RC<n>` batch. | validate-review-dir.py:1785 |
| `surviving candidate/verdict <c>/<v> has <n> root-cause trigger rows` | Survivor lacks (or duplicates) its root-cause row. | Add exactly one root-cause trigger row for it. | validate-review-dir.py:1788 |
| `root family <id> is split across RC batches <b>` | One family scheduled into several batches. | Put every member of the family in a single RC batch. | validate-review-dir.py:1794 |
| `root family <id> is scheduled to <b> but <x> is missing` | A family member is absent from its batch. | Add the missing member to that batch. | validate-review-dir.py:1802 |
| `<file>: Root-family analysis has wrong columns` | Header mismatch. | Copy the `## Root-family analysis` header from the template. | validate-review-dir.py:1818 |
| `<file>: root family <id> injects member <m> assigned by affinity to <other>` | The RC artifact reassigned a member. | Keep the affinity artifact's assignment; it is authoritative. | validate-review-dir.py:1832 |
| `<file>: root family <id> has blank <column>` | Empty required cell. | Fill it in. | validate-review-dir.py:1839 |
| `<file>: root family <id> has malformed Suggested edit decision` | The decision line does not match `- **Suggested edit:** applicable — ...` / `omitted — ...`. | Write it exactly as `- **Suggested edit:** applicable — <target>` or `- **Suggested edit:** omitted — <specific reason>`. | validate-review-dir.py:1848, :39 |
| `<file>: root family <id> has <n> canonical RC Suggested edit decisions; expected exactly one` | Several decisions for one family. | Keep exactly one canonical decision per root family. | validate-review-dir.py:1858 |
| `<file>: root family <id> Suggested edit cell must be '<x>'` | Table cell disagrees with the canonical decision. | Set the cell to the required literal. | validate-review-dir.py:1871 |
| `<file>: root family <id> has <n> Root-family analysis rows` | Zero or duplicate analysis rows. | Keep exactly one per family. | validate-review-dir.py:1876 |
| `root-cause Suggested edit decision <id> is defined more than once` | Duplicate RC decision IDs across artifacts. | Define each RC decision once. | validate-review-dir.py:385 |
| `root-cause row <r> with a Suggested edit decision lacks an exact Root family field` | Decision without a family binding. | Add the `Root family: RF<nnn>` field to the row. | validate-review-dir.py:397 |
| `root-cause row <r> has malformed applicable Suggested edit target` | Target is not `replaces path:start-end`. | Write `replaces path/to/file.cc:120-124`. | validate-review-dir.py:404, :47 |
| `root-cause row <r> applicable Suggested edit lacks selected lines` | No selected-lines fence. | Add the selected-lines fenced block. | validate-review-dir.py:409 |
| `root-cause row <r> applicable Suggested edit lacks a replacement block` | No ```suggestion fence. | Add the ```suggestion block (see §11). | validate-review-dir.py:414 |
| `root-cause row <r> has a non-specific Suggested edit omission reason` | Reason is one of `n/a`, `none`, `not applicable`, `no suggestion`, `omitted`. | Give a concrete reason explaining why no edit is proposable. | validate-review-dir.py:419, :51 |
| `root-cause row <r> marks Suggested edit omitted but contains selected/replacement fences` | Contradiction. | Remove the fences, or change the decision to `applicable`. | validate-review-dir.py:424 |

---

### 4.13 `reconciliation.md` (`validate_reconciliation`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `reconciliation promotion exception has invalid root family '<id>'` | Exception names a bad `RF` ID. | Correct it to an existing `RF<nnn>`. | validate-review-dir.py:3790 |
| `root-family promotion exception <id> lacks justification with code/artifact evidence` | Uncited exception. | Add a `path:line` or artifact-pointer citation to the justification. | validate-review-dir.py:3801 |
| `reconciliation duplicates merge-equivalence row <a> → <b>` | Duplicate merge-equivalence entry. | Keep exactly one. | validate-review-dir.py:3817 |
| `reconciliation merge-equivalence row has invalid IDs '<a>'/'<b>'` | Malformed row IDs. | Use valid `ROW_ID` values on both sides. | validate-review-dir.py:3826 |
| `merge <a> → <b> cites missing or empty review artifact <p> for <k>` | The cited artifact pointer resolves to nothing. | Point at a real, non-empty file inside the review directory. | validate-review-dir.py:3842, :64 |
| `merge <a> → <b> lacks cited <k>` | A required citation is missing. | Add the named citation. | validate-review-dir.py:3850 |
| `reconciliation row <r> has blank disposition` | Empty disposition cell. | Fill in a disposition. | validate-review-dir.py:3862 |
| `reconciliation row <r> has malformed merge disposition; expected 'merged → <survivor-row-id>'` | Bad merge syntax. | Write `merged → <ROW-ID>`. | validate-review-dir.py:3879 |
| `reconciliation row <r> uses forbidden bare downgraded disposition; use 'promoted → F<number>' at the calibrated severity` | Bare `downgraded`. | Replace with `promoted → F<n>` at the correct severity. | validate-review-dir.py:3885 |
| `reconciliation row <r> has malformed <k> disposition; expected '<k> → <P><number>' with an optional parenthesized note` | Bad disposition syntax. | Write `<kind> → <PREFIX><n> (optional note)`. | validate-review-dir.py:3897 |
| `reconciliation synthesis item <i> is assigned to both <a> and <b>` | Two rows own one synthesis item. | Give each item a single owning row. | validate-review-dir.py:3909 |
| `reconciliation row <r> merges into itself` | Self-merge. | Point the merge at a different survivor. | validate-review-dir.py:3924 |
| `reconciliation row <r> merges into unknown survivor <s>` | Survivor does not exist. | Correct the survivor row ID. | validate-review-dir.py:3927 |
| `reconciliation merge <a> → <b> uses a merged survivor; target the final verdict-owning row directly` | Chained merge. | Merge directly into the final verdict-owning row. | validate-review-dir.py:3933 |
| `reconciliation merge <a> → <b> lacks an exact Merge equivalence row` | Disposition without a merge-equivalence entry. | Add the matching Merge equivalence row. | validate-review-dir.py:3939 |
| `reconciliation merge <a> → <b> has no verdict-owning survivor` | Survivor has no verdict. | Merge into a row that owns a verdict. | validate-review-dir.py:3945 |
| `merge <a> → <b> does not cite the survivor's exact verdict <v> <x>` | Merge does not quote the survivor's verdict. | Cite the survivor's exact verdict in the merge row. | validate-review-dir.py:3962 |
| `reconciliation merge <a> → <b> hides <x> behind survivor verdict <v>` | The merge would suppress a stronger finding. | Do not merge; keep the stronger row separate, or re-verdict the survivor. | validate-review-dir.py:3971 |
| `reconciliation merge survivor <s> has <v> verdict but disposition '<d>'` | Survivor's disposition contradicts its verdict. | Set the disposition implied by the verdict. | validate-review-dir.py:3985 |
| `reconciliation merge <a> → <b> crosses root families <x>/<y>` | Cross-family merge. | Only merge within a root family. | validate-review-dir.py:3997 |
| `reconciliation has foreign Merge equivalence row <a> → <b> without a matching disposition` | Orphan merge-equivalence row. | Delete it, or add the matching disposition. | validate-review-dir.py:4004 |
| `reconciliation candidate <c> has <v> verdict but disposition '<d>'; expected <e>` | Disposition contradicts the verdict. | Set the expected disposition. | validate-review-dir.py:4036 |
| `row <r> has <n> reconciliation dispositions` | Zero or duplicate dispositions. | Keep exactly one per row. | validate-review-dir.py:4043 |
| `reconciliation references unknown row <r>` | Unknown row ID. | Correct the ID. | validate-review-dir.py:4046 |
| `root family <id> promotes multiple findings <x> without a Root-family promotion exception` | Several promotions from one family. | Promote one finding, or add a justified Root-family promotion exception. | validate-review-dir.py:4049 |
| `reconciliation.md lacks ## Pre-output gate` | Section missing. | Add the `## Pre-output gate` section. | validate-review-dir.py:4057 |
| `pre-output gate line <n> is not affirmatively complete` | A gate line is unticked or hedged. | Complete the work and state the line affirmatively. | validate-review-dir.py:4067 |
| `reconciliation Freshness gate is not affirmative with a delivery-gate.md citation` | Freshness line missing or uncited. | Run `refresh-delivery-gate.py <REVIEW_DIR>`, then cite `delivery-gate.md` affirmatively. | validate-review-dir.py:5179 |

### 4.14 Synthesis cards (`validate_synthesis`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `synthesis/index.md duplicates item <i>` | Duplicate index entry. | Keep one entry per item. | validate-review-dir.py:4093 |
| `synthesis/index.md contains foreign item <i>; no promoted/question reconciliation disposition owns it` | Index lists an unowned item. | Remove it, or add the owning reconciliation disposition. | validate-review-dir.py:4097 |
| `synthesis card is missing: <path>` | Indexed card file absent. | Write the card. | validate-review-dir.py:4107 |
| `synthesis finding card <i> lacks a non-empty 'Suggested edit decision' field` | Card missing the decision line. | Add `- Suggested edit decision: applicable — ...` or `omitted — ...`. | validate-review-dir.py:4113, :43 |
| `synthesis finding card <i> lacks exact Root cause / Root family binding fields` | Card missing bindings. | Add both `Root cause:` and `Root family:` fields. | validate-review-dir.py:4133 |
| `synthesis finding card <i> erases canonical root-cause Suggested edit decision(s) <x>` | Card dropped an RC decision. | Carry the RC decision through to the card unchanged. | validate-review-dir.py:4149 |
| `synthesis finding card <i> binds Suggested edit to an RC row outside its root family` | Cross-family binding. | Bind to an RC row inside the card's own root family. | validate-review-dir.py:4159 |
| `synthesis finding card <i> erases authoritative root family <rf>` | Card dropped the family. | Restore the authoritative `Root family:` value. | validate-review-dir.py:4165 |
| `synthesis finding card <i> binds owner <o> from <a> to unrelated <b>` | Owner rebinding. | Keep the authoritative owner binding. | validate-review-dir.py:4175 |
| `synthesis finding card <i> Root family differs from authoritative affinity` | Card disagrees with the affinity artifact. | Copy the family from the affinity artifact. | validate-review-dir.py:4185 |
| `synthesis finding card <i> has a Root family without a Root cause binding` | Family without cause. | Add the `Root cause:` field. | validate-review-dir.py:4194 |
| `synthesis finding card <i> has malformed applicable Suggested edit target` | Target is not `replaces path:start-end`. | Write `replaces path/to/file.cc:120-124`. | validate-review-dir.py:4200 |
| `synthesis finding card <i> applicable Suggested edit has <n> suggestion blocks; expected exactly one` | Zero or several ```suggestion fences. Zero usually means the closing fence is indented differently from the opening one — see §11. | Keep exactly one ```suggestion block, with the closing ``` at the same indentation as the opening fence. | validate-review-dir.py:4205, :328 |
| `synthesis finding card <i> applicable Suggested edit lacks selected lines` | No selected-lines block. | Add it. | validate-review-dir.py:4214 |
| `synthesis finding card <i> applicable Suggested edit lacks a canonical RC decision` | No RC decision to anchor the edit. | Add the canonical RC decision, then bind the card to it. | validate-review-dir.py:4220 |
| `synthesis finding card <i> Suggested edit differs from its root-cause decision` | Card text diverged from the RC decision. | Make the card's decision byte-identical to the RC decision. | validate-review-dir.py:4235, :4267 |
| `synthesis finding card <i> has a non-specific Suggested edit omission reason` | Reason is `n/a`, `none`, `not applicable`, `no suggestion`, or `omitted`. | Give a concrete reason. | validate-review-dir.py:4241, :51 |
| `synthesis finding card <i> marks Suggested edit omitted but contains a suggestion block` | Contradiction. | Remove the block, or mark the decision `applicable`. | validate-review-dir.py:4246 |
| `synthesis finding card <i> cites unknown RC Suggested edit decision <x>` | Bad RC decision ID. | Correct the ID. | validate-review-dir.py:4253 |
| `synthesis card exceeds profile evidence-card budget: <p> (<x> > <y> bytes)` | Card too large. | Shorten the card. | validate-review-dir.py:4274 |
| `synthesis card byte count mismatch for <p>: <a> != <b>` | `synthesis/index.md` byte count is stale. | Update the index's byte count to the card's actual size. | validate-review-dir.py:4281 |
| `synthesis/index.md has invalid byte count for <p>` | Non-integer byte count. | Write the integer size. | validate-review-dir.py:4283 |
| `synthesis item <i> cites unknown source row <r>` | Bad source row ID. | Correct the ID. | validate-review-dir.py:4290 |
| `synthesis item <i> omits its Root cause row <r> from source rows` | Source list incomplete. | Add the RC row to the card's source rows. | validate-review-dir.py:4300 |
| `synthesis item <i> omits its owning reconciliation row <r> from source rows` | Source list incomplete. | Add the reconciliation row. | validate-review-dir.py:4305 |
| `reconciliation <k> <d> for row <r> has no synthesis card` | Promoted item without a card. | Write the synthesis card. | validate-review-dir.py:4312 |
| `large synthesis handoff lacks draft-parts/*.md` | Sharded synthesis with no parts. | Produce `draft-parts/*.md`. | validate-review-dir.py:4319 |
| `large synthesis handoff lacks required draft-parts/FRAME.md` | Frame part missing. | Write `draft-parts/FRAME.md`. | validate-review-dir.py:4321 |
| `large synthesis handoff lacks draft part for <i>` | A card has no draft part. | Write the missing part. | validate-review-dir.py:4324 |
| `assembly node <n> uses a glob/range instead of exact child paths` | Assembly manifest used `*` or a range. | List every child path explicitly. | validate-review-dir.py:4335 |
| `assembly node <n> repeats a child path` | Duplicate child. | De-duplicate. | validate-review-dir.py:4344 |
| `assembly node <n> has missing child <p>` | Child file absent. | Create it, or remove it from the node. | validate-review-dir.py:4350 |
| `assembly node <n> input bytes mismatch: <a> != <b>` | Recorded bytes are stale. | Recompute the node's input byte total. | validate-review-dir.py:4358 |
| `assembly node <n> exceeds profile worker-input budget (<x> > <y> bytes)` | Node too large. | Split the node into more children. | validate-review-dir.py:4364 |
| `assembly node <n> has invalid input bytes` | Non-integer. | Write the integer total. | validate-review-dir.py:4369 |
| `assembly node <n> has <c> children` | Wrong fan-out. | Rebuild the assembly tree to the allowed fan-out. | validate-review-dir.py:4372 |
| `assembly node <n> is not complete` | Node's work unit unfinished. | Complete it. | validate-review-dir.py:4374 |
| `root assembly node does not directly include FRAME.md` | Frame is nested. | Make `FRAME.md` a direct child of the root node. | validate-review-dir.py:4378 |
| `large synthesis handoff lacks a valid assembly manifest` | No manifest. | Write the assembly manifest. | validate-review-dir.py:4380 |
| `large synthesis handoff lacks a root draft-review assembly node` | No root node. | Add the root node. | validate-review-dir.py:4382 |

---

### 4.15 Final output: `output-coverage.tsv`, draft sections, delivery gate, challenge (`validate_output_coverage`, `validate_draft_sections`, `validate_final`)

| Message (substring you will actually see) | What it means | Fix | Source |
| --- | --- | --- | --- |
| `output-coverage.tsv is missing; promoted findings/questions lack exact draft/Gerrit fragment coverage` | No coverage table. | Write `output-coverage.tsv` with one row per synthesis item. | validate-review-dir.py:4433 |
| `output-coverage.tsv has wrong columns or order` | Header mismatch. | Restore to `item kind draft_path draft_bytes draft_sha256 gerrit_path gerrit_bytes gerrit_sha256`. | validate-review-dir.py:4442, :4391 |
| `cannot parse output-coverage.tsv: <err>` | Not valid TSV. | Rewrite the file as tab-separated. | validate-review-dir.py:4446 |
| `output-coverage.tsv line <n> has the wrong number of tab-separated fields` | Ragged row. | Pad the row to eight tab-separated fields. | validate-review-dir.py:4612 |
| `output-coverage.tsv duplicates item <i>` | Two rows for one item. | Keep one. | validate-review-dir.py:4619 |
| `output-coverage.tsv contains foreign item <i>; no synthesis card owns it` | Row for an unknown item. | Delete the row, or write the synthesis card. | validate-review-dir.py:4624 |
| `output coverage <i> kind <a> does not match synthesis kind <b>` | `kind` disagrees with the card. | Copy the kind from the synthesis card. | validate-review-dir.py:4630 |
| `output coverage <i> <k>_path must be <x>, found <y>` | Path column points at the wrong file. | Set it to `draft-review.md` / `gerrit-comments.md` (or the indexed section path). | validate-review-dir.py:4469 |
| `output coverage <i> lacks <k> fragment <f>` | The named fragment is absent from the output file. | Add the fragment to the draft/Gerrit output. | validate-review-dir.py:4476 |
| `output coverage <i> has empty <k> fragment` | Zero-length fragment. | Write real content. | validate-review-dir.py:4480 |
| `output coverage <i> <k> byte count mismatch: <a> != <b>` | Stale byte count. | Recompute the byte count for that fragment. | validate-review-dir.py:4484 |
| `output coverage <i> has invalid <k>_bytes '<v>'` | Non-integer. | Write the integer byte count. | validate-review-dir.py:4489 |
| `output coverage <i> <k> hash mismatch: <a> != <b>` | Stale sha256. | Recompute the sha256 for that fragment. | validate-review-dir.py:4494 |
| `output coverage <i> <k> fragment occurs <n> times in final <x> output; expected exactly one` | Duplicated fragment. | De-duplicate the fragment in the output file. | validate-review-dir.py:4500 |
| `output coverage <i> draft fragment is not UTF-8` | Encoding problem. | Re-save the draft as UTF-8. | validate-review-dir.py:4649 |
| `output coverage <i> draft fragment lacks exact '- **Synthesis item:** <i>' marker` | Marker missing or reworded. | Add the marker line verbatim, including the bold markers. | validate-review-dir.py:4653 |
| `output coverage <i> draft fragment lacks non-empty '<field>' field` | A required draft field is empty. | Fill the field in. | validate-review-dir.py:4668 |
| `output coverage <i> Gerrit fragment is not UTF-8` | Encoding problem. | Re-save `gerrit-comments.md` as UTF-8. | validate-review-dir.py:4688 |
| `output coverage <i> Gerrit fragment lacks a repo-relative path:line target` | No target in the Gerrit comment. | Add a `path/to/file.cc:123` target line. | validate-review-dir.py:4693 |
| `question <i> must use '-' for all Gerrit coverage fields` | A `question` item has Gerrit columns filled. | Set `gerrit_path`, `gerrit_bytes`, `gerrit_sha256` to `-`. | validate-review-dir.py:4704 |
| `synthesis item <i> has no output-coverage.tsv row` | Item never covered. | Add its coverage row. | validate-review-dir.py:4709 |
| `output coverage <i> draft fragment lacks a non-empty 'Suggested edit' field` | Missing decision field. | Add `- **Suggested edit:** applicable — ...` / `omitted — ...`. | validate-review-dir.py:4513 |
| `output coverage <i> Suggested edit decision differs from its synthesis card` | Drift from the card. | Copy the card's decision verbatim. | validate-review-dir.py:4526 |
| `output coverage <i> has a non-specific Suggested edit omission reason` | Reason in `NON_SPECIFIC_OMISSION`. | Give a concrete reason. | validate-review-dir.py:4532, :51 |
| `output coverage <i> marks Suggested edit omitted but contains a suggestion block` | Contradiction. | Remove the block, or mark it `applicable`. | validate-review-dir.py:4537 |
| `output coverage <i> has malformed applicable Suggested edit target; expected 'replaces path:start-end'` | Bad target syntax. | Write `replaces path/to/file.cc:120-124`. | validate-review-dir.py:4545 |
| `output coverage <i> Suggested edit target range is reversed` | `start > end`. | Swap the endpoints. | validate-review-dir.py:4553 |
| `output coverage <i> Suggested edit selects <n> lines; maximum is 10` | Range too wide. | Narrow the selection to at most 10 lines. | validate-review-dir.py:4558 |
| `output coverage <i> Suggested edit targets unchanged or unknown file <f>` | Target file is not in the CL's changed files. | Target a file the CL actually touches. | validate-review-dir.py:516 |
| `output coverage <i> Suggested edit target is not a normalized repo-relative path` | Absolute path, `./`, or `..` in the target. | Use a clean repo-relative path. | validate-review-dir.py:468 |
| `output coverage <i> cannot verify Suggested edit against the pinned worktree` | Worktree unavailable. | Restore the pinned worktree (§4.2) and re-run. | validate-review-dir.py:526 |
| `output coverage <i> cannot read Suggested edit target from the pinned revision: <err>` | File unreadable at the pinned SHA. | Check the path spelling against the pinned revision. | validate-review-dir.py:556 |
| `output coverage <i> Suggested edit range <r> is outside the pinned file's <n> lines` | Line numbers past EOF. | Use line numbers from the pinned revision, not your local checkout. | validate-review-dir.py:564 |
| `output coverage <i> Suggested edit selected lines do not match the pinned changed-side range` | The quoted "selected lines" text differs from the file. | Copy the selected lines byte-for-byte from the pinned file. | validate-review-dir.py:571 |
| `output coverage <i> Suggested edit range <r> does not intersect a changed-side hunk in the pinned patch` | Suggestion targets untouched lines. | Move the suggestion onto lines the CL changes. | validate-review-dir.py:584 |
| `output coverage <i> Gerrit fragment has <n> exact target declarations for <f>; expected one` | Several target lines. | Keep exactly one target declaration. | validate-review-dir.py:482 |
| `output coverage <i> Gerrit fragment has <n> standalone target declarations; expected exactly one total` | Extra standalone targets. | Keep exactly one. | validate-review-dir.py:493 |
| `output coverage <i> applicable Suggested edit requires exactly one suggestion block in both draft and Gerrit fragments (found <a> and <b>)` | Block count mismatch. A count of `0` usually means an indentation mismatch between the opening and closing fences (§11). | Put exactly one ```suggestion block in each fragment, with matching fence indentation. | validate-review-dir.py:4570 |
| `output coverage <i> draft and Gerrit suggestion blocks differ` | The two copies diverge. | Make them byte-identical. | validate-review-dir.py:4578 |
| `output coverage <i> suggestion block differs from its synthesis card` | Drift from the card. | Copy the card's block verbatim. | validate-review-dir.py:4588 |
| `output coverage <i> Suggested edit has <n> replacement lines; maximum is 20` | Replacement too long. | Shrink the replacement to at most 20 lines. | validate-review-dir.py:4594 |
| `output coverage <i> Suggested edit contains a placeholder or elision` | A replacement line is exactly `...`, `…`, `<replacement>`, `<code>`, or `placeholder`. | Write the real replacement code; never elide. | validate-review-dir.py:4604, :4601 |
| `large draft exceeds profile worker-input budget but lacks draft-sections/index.tsv` | Big draft, no section index. | Produce `draft-sections/index.tsv`. | validate-review-dir.py:4728 |
| `draft-sections/index.tsv has wrong columns or order` | Header mismatch. | Restore to `revision order section type draft_path draft_bytes draft_sha256 gerrit_path gerrit_bytes gerrit_sha256 cards rows global_frame`. | validate-review-dir.py:4738, :4386 |
| `cannot parse draft-sections/index.tsv: <err>` | Not valid TSV. | Rewrite as tab-separated. | validate-review-dir.py:4742 |
| `draft-sections/index.tsv contains no section rows` | Header only. | Add the section rows. | validate-review-dir.py:4745 |
| `draft-sections/index.tsv:<N>: invalid <col> '<v>'` | Bad cell value. | Correct that cell. | validate-review-dir.py:4762 |
| `draft-sections/index.tsv:<N>: missing <k> <p>` | Referenced section file absent. | Create the file. | validate-review-dir.py:4768 |
| `draft-sections/index.tsv:<N>: invalid section '<s>'` | Bad section name. | Use a recognized section name. | validate-review-dir.py:4777 |
| `draft-sections/index.tsv duplicates section <s>` | Duplicate section. | Keep one row per section. | validate-review-dir.py:4782 |
| `draft section <s> has invalid order '<o>'` | Non-integer order. | Use integers `1..N`. | validate-review-dir.py:4790 |
| `draft-sections/index.tsv duplicates order <o>` | Two sections share an order. | Renumber. | validate-review-dir.py:4793 |
| `draft-sections/index.tsv order values are not unique contiguous 1..N` | Gaps in the ordering. | Renumber contiguously from 1. | validate-review-dir.py:4867 |
| `draft section <s> revision <a> does not match draft revision <b>` | Stale section revision. | Bump every section's `revision` to the current `Draft revision`. | validate-review-dir.py:4796 |
| `draft section <s> has invalid global_frame value` | Not a boolean token. | Use the template's allowed values. | validate-review-dir.py:4801 |
| `draft-sections/index.tsv has <n> global-frame sections, expected 1` | Zero or several frames. | Mark exactly one section as the global frame. | validate-review-dir.py:4863 |
| `draft-sections/index.tsv reuses draft_path <p>` | Two sections share a draft file. | Give each section its own file. | validate-review-dir.py:4810 |
| `draft-sections/index.tsv reuses gerrit_path <p>` | Same, for Gerrit files. | Give each section its own file. | validate-review-dir.py:4814 |
| `draft section <s> draft byte count mismatch: <a> != <b>` | Stale byte count. | Recompute it. | validate-review-dir.py:4826 |
| `draft section <s> has invalid draft_bytes value` | Non-integer. | Write the integer size. | validate-review-dir.py:4831 |
| `draft section <s> has invalid draft_sha256` | Malformed hash. | Write the 64-char lowercase hex digest. | validate-review-dir.py:4834 |
| `draft section <s> draft_sha256 mismatch: <a> != <b>` | Stale hash. | Recompute it. | validate-review-dir.py:4836 |
| `draft section <s> Gerrit byte count mismatch: <a> != <b>` | Stale byte count. | Recompute it. | validate-review-dir.py:4846 |
| `draft section <s> has invalid gerrit_bytes value` | Non-integer. | Write the integer size. | validate-review-dir.py:4851 |
| `draft section <s> has invalid gerrit_sha256` | Malformed hash. | Write the 64-char digest. | validate-review-dir.py:4854 |
| `draft section <s> gerrit_sha256 mismatch: <a> != <b>` | Stale hash. | Recompute it. | validate-review-dir.py:4856 |
| `draft-review.md is not the exact indexed section concatenation` | Whole file ≠ sections joined in order. | Regenerate `draft-review.md` by concatenating the indexed sections in `order`. | validate-review-dir.py:4873 |
| `gerrit-comments.md is not the exact indexed section concatenation` | Same, for Gerrit. | Regenerate by concatenation. | validate-review-dir.py:4876 |
| `draft-review.md does not state the full pinned revision SHA` | SHA absent from the draft. | Put the full 40-char pinned SHA in the draft header. | validate-review-dir.py:4887 |
| `draft-review.md does not state the reviewed patchset` | No `patchset <n>` / `PS<n>`. | Add the patchset to the draft header. | validate-review-dir.py:4889 |
| `draft-review.md lacks a positive integer Draft revision` | Missing/zero `Draft revision`. | Add `Draft revision: 1` (incrementing on each revision). | validate-review-dir.py:4892 |
| `gerrit-comments.md contains a local path/URL or placeholder inline` | See §11 — matches `file://`, `/tmp/`, `/home/`, **or any `<...>` text**. | Remove local paths and placeholders; for genuine code containing angle brackets, see the workaround in §11. | validate-review-dir.py:4894, :4893 |
| `<file> Pinned field lacks a full revision SHA` | Delivery gate missing the pinned SHA. | Re-run `refresh-delivery-gate.py <REVIEW_DIR>`. | validate-review-dir.py:4915 |
| `<file> Pinned SHA does not match pin.md` | Gate disagrees with the pin. | Re-run `refresh-delivery-gate.py <REVIEW_DIR>`. | validate-review-dir.py:4917 |
| `<file> Gerrit current field lacks a full revision SHA` | Missing current SHA. | Re-run `refresh-delivery-gate.py <REVIEW_DIR>`. | validate-review-dir.py:4919 |
| `<file> is not a completed freshness decision` | Gate artifact is a stub. | Re-run `refresh-delivery-gate.py <REVIEW_DIR>`. | validate-review-dir.py:4921 |
| `<file> has non-deliverable result: <r>` | The CL moved on; the review is stale. | Re-fetch the current patchset into a fresh review directory, or document a trivial delta in `patchset-delta.md`. | validate-review-dir.py:4925 |
| `<file> does not contain an affirmative Gate line` | No affirmative gate statement. | Re-run `refresh-delivery-gate.py <REVIEW_DIR>`. | validate-review-dir.py:4928 |
| `<file> claims current but Gerrit current differs from pin.md` | Contradiction. | Re-run `refresh-delivery-gate.py <REVIEW_DIR>`. | validate-review-dir.py:4930 |
| `material patchset delta cannot be delivered from the old review directory` | A new patchset materially changed the CL. | Start a fresh review at the new patchset: `fetch-cl.sh <CL> <NEW_PS>`. | validate-review-dir.py:4935 |
| `patchset-delta.md does not identify the pinned old SHA` | Delta note incomplete. | Add the pinned old SHA. | validate-review-dir.py:4939 |
| `patchset-delta.md does not identify the delivered Gerrit-current SHA` | Delta note incomplete. | Add the current SHA. | validate-review-dir.py:4941 |
| `patchset-delta.md does not classify the inspected delta as trivial` | Delta not classified. | State explicitly that the delta is trivial, with evidence — or restart the review. | validate-review-dir.py:4943 |
| `trivial-delta draft does not state the delivered Gerrit-current SHA` | Draft header stale. | Add the delivered current SHA to the draft. | validate-review-dir.py:4945 |
| `trivial-delta draft does not state the delivered Gerrit-current patchset` | Draft header stale. | Add the delivered patchset number. | validate-review-dir.py:4952 |
| `challenge.md does not point to a completed round index` | Challenge round unfinished. | Complete the challenge round and point `challenge.md` at its index. | validate-review-dir.py:4959 |
| `<file> lacks a positive integer Draft revision` | Missing revision. | Add `Draft revision: <n>`. | validate-review-dir.py:4965 |
| `latest challenge audited draft revision <a>, current draft is <b>` | The draft changed after the challenge. | Re-run the challenge round against the current draft revision. | validate-review-dir.py:4967 |
| `<file> challenge revision <a> does not match challenged draft revision <b>` | Revision mismatch. | Align the challenge's recorded revision with the draft it audited. | validate-review-dir.py:4973 |
| `latest challenge index is not a pass: <r>` | Challenge found issues. | Fix the issues it lists, then re-run the challenge round. | validate-review-dir.py:4978 |
| `<file> has invalid challenge shard '<s>'` | Bad shard ID. | Use the template's shard ID form. | validate-review-dir.py:4997 |
| `<file> duplicates challenge shard <s>` | Duplicate shard. | Keep one row per shard. | validate-review-dir.py:4999 |
| `<file> shard <s> lacks scope/coverage` | Shard has no scope. | State the shard's scope and coverage token. | validate-review-dir.py:5002 |
| `<file> shard <s> global scope/token mismatch` | Global-consistency shard mislabelled. | Align the shard's scope with its coverage token. | validate-review-dir.py:5015 |
| `challenge shard <s> has missing/empty brief` | No brief. | Write and seal the shard brief. | validate-review-dir.py:5025 |
| `challenge shard missing/empty: <p>` | Shard artifact absent. | Produce the shard artifact. | validate-review-dir.py:5032 |
| `<file> shard <s> lacks an artifact` | No artifact recorded. | Record the shard's artifact path. | validate-review-dir.py:5034 |
| `passing challenge shard <s> still lists issues` | Contradiction. | Either resolve the issues or mark the shard failing. | validate-review-dir.py:5036 |
| `<file>: sectioned large-draft challenger receives a whole draft/Gerrit output` | A sectioned challenger was given the whole file. | Seal only the assigned section files as inputs. | validate-review-dir.py:5040 |
| `<file>: sectioned challenger uses a whole-section glob` | Glob instead of exact paths. | List exact section paths. | validate-review-dir.py:5045 |
| `sectioned challenge shard <s> has no input-manifest work row` | Shard never sealed. | Seal the shard with `seal-work-unit.py`. | validate-review-dir.py:5058 |
| `input-manifest work <w> does not name its challenge brief` | Self row missing. | Re-seal with the correct `--brief`. | validate-review-dir.py:5064 |
| `challenge shard <s> assigns unknown card <c>` | Bad card ID. | Correct the card ID. | validate-review-dir.py:5093 |
| `input-manifest work <w> lacks assigned section <s>` | Assigned section not sealed as an input. | Re-seal with `--input section=<path>`. | validate-review-dir.py:5097 |
| `input-manifest work <w> lacks assigned frame <f>` | Frame not sealed. | Re-seal with `--input frame=<path>`. | validate-review-dir.py:5101 |
| `input-manifest work <w> lacks assigned card <c>` | Card not sealed. | Re-seal with `--input card=<path>`. | validate-review-dir.py:5105 |
| `input-manifest work <w> has unassigned section <s>` | Sealed a section the shard was not assigned. | Remove that `--input` and re-seal. | validate-review-dir.py:5110 |
| `input-manifest work <w> has unknown frame <f>` | Unknown frame input. | Remove or correct it. | validate-review-dir.py:5115 |
| `input-manifest work <w> has unassigned card <c>` | Sealed an unassigned card. | Remove that `--input` and re-seal. | validate-review-dir.py:5119 |
| `<file>: references unassigned draft section <s>` | Shard talked about a section it does not own. | Restrict the shard's findings to its assigned sections. | validate-review-dir.py:5131 |
| `<file>: assigned section <s> lacks draft input` | Missing draft input for an assigned section. | Seal `--input section=<draft section path>`. | validate-review-dir.py:5139 |
| `<file>: assigned section <s> lacks Gerrit input` | Missing Gerrit input. | Seal `--input section=<gerrit section path>`. | validate-review-dir.py:5144 |
| `<file>: does not record both audited hashes for section <s>` | Shard recorded only one hash. | Record both the draft and Gerrit sha256 it audited. | validate-review-dir.py:5152 |
| `<file> has no complete challenge shard roster` | Roster incomplete. | Complete every shard in the roster. | validate-review-dir.py:5157 |
| `<file> has <n> global-consistency shards, expected 1` | Zero or several global shards. | Keep exactly one global-consistency shard. | validate-review-dir.py:5159 |
| `challenge coverage token <t> appears <n> times` | Duplicate coverage token. | Use each coverage token once. | validate-review-dir.py:5170 |
| `challenge coverage names unknown token <t>` | Unknown token. | Correct the token. | validate-review-dir.py:5173 |

---
