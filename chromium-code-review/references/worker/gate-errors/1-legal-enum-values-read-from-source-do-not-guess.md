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

## 1. Legal enum values (read from source, do not guess)

| Flag / column | Legal values (verbatim) | Source |
| --- | --- | --- |
| `validate-review-dir.py --phase` | `auto`, `pin`, `collection`, `verification`, `reconciliation`, `final` | validate-review-dir.py:34 (`PHASES`), :5198 (`choices=("auto", *PHASES)`) |
| `seal-work-unit.py --tier` | `frontier`, `inherit`, `mechanical`, `standard` | seal-work-unit.py:35 (`TIERS`), :192 |
| `seal-work-unit.py --input ROLE=` | `assigned`, `candidate-packet`, `card`, `control`, `frame`, `prestate`, `reference`, `section` | seal-work-unit.py:31 (`ROLES`) |
| `input-manifest.tsv` `role` column | the eight `ROLES` above **plus** `brief` (the self row, written by the sealer) | validate-review-dir.py:229 (`INPUT_MANIFEST_ROLES`) |
| `orchestration.tsv` `state` column | `queued`, `running`, `partial`, `retryable`, `needs-repair`, `complete`, `terminated` | validate-review-dir.py:221 (`MANIFEST_STATES`) |
| `orchestration.tsv` `tier` column | `mechanical`, `standard`, `frontier`, `inherit` | validate-review-dir.py:174 (`MANIFEST_TIERS`) |
| tier ordering (for "below its floor" errors) | `mechanical` < `standard` < `frontier`; `inherit` is unordered | validate-review-dir.py:175 (`TIER_ORDER`) |
| `worktree-lease.py` subcommands | `acquire`, `write-state`, `validate-state`, `heartbeat`, `release`, `release-token`, `check`, `holder-of`, `holders`, `gc` | worktree-lease.py:920-971 |
| gate verdicts (VTER.md) | `PROVEN`, `REJECTED`, `UNPROVEN` | validate-review-dir.py:219 (`GATE_VERDICTS`) |
| candidate classes | `general`, `contract`, `async-lifetime`, `style-convention`, `state-protocol`, `platform` | validate-review-dir.py:189 (`CLASS_OBLIGATIONS`) |
| trace obligations | `local-proof`, `base-contract`, `caller-reachability`, `callee/backend-implementation`, `async-operation-owner`, `destruction/cancellation`, `platform-branches`, `style-authority` | validate-review-dir.py:179 (`OBLIGATIONS`) |
| consistency-audit checks | `contradictory assumptions`, `invariant-owner collisions`, `style-authority scope`, `lifetime operation owner`, `reachability termination`, `repeated local fixes` | validate-review-dir.py:211 (`CONSISTENCY_CHECKS`) |
| specialist prior assessors | `semantic-state`, `adversarial-integration` | validate-review-dir.py:163 |
| specialist likelihood values | `low`, `medium`, `high` | build-review-indexes.py:366; validate-worker-artifact.py:284 |
| specialist probe result | `clean` or `escalate` | validate-review-dir.py:1075; validate-worker-artifact.py:333 |
| deterministic index file names | `inventory.tsv`, `topology.tsv`, `specialist-priors.tsv`, `candidates.tsv`, `verdicts.tsv`, `reconciliation.tsv`, `manifest.json` | validate-review-dir.py:247 (`DETERMINISTIC_INDEX_NAMES`) |

### Exact column tuples

| File | Ordered columns (exact, tab-separated) | Source |
| --- | --- | --- |
| `orchestration.tsv` | `phase`, `work_id`, `attempt`, `state`, `tier`, `task_id`, `brief`, `artifact`, `remaining_scope`, `depends_on` | seal-work-unit.py:23 (`ORCHESTRATION_COLUMNS`); validate-review-dir.py:170 (`MANIFEST_COLUMNS`) |
| `input-manifest.tsv` | `work_id`, `attempt`, `phase`, `brief`, `input_path`, `role`, `bytes`, `sha256` | seal-work-unit.py:27 (`INPUT_COLUMNS`); validate-review-dir.py:225 (`INPUT_MANIFEST_COLUMNS`) |
| `draft-sections/index.tsv` | `revision`, `order`, `section`, `type`, `draft_path`, `draft_bytes`, `draft_sha256`, `gerrit_path`, `gerrit_bytes`, `gerrit_sha256`, `cards`, `rows`, `global_frame` | validate-review-dir.py:4386 (`DRAFT_SECTION_COLUMNS`) |
| `output-coverage.tsv` | `item`, `kind`, `draft_path`, `draft_bytes`, `draft_sha256`, `gerrit_path`, `gerrit_bytes`, `gerrit_sha256` | validate-review-dir.py:4391 (`OUTPUT_COVERAGE_COLUMNS`) |

> [!IMPORTANT]
> Both TSVs are order-sensitive. `has wrong columns or order` means the header
> row does not match the tuple above character-for-character; do not "fix" it by
> reordering data rows.

### Roster identities (`plan.md omits roster entry` / `invents or renames`)

Thread names must match `ROSTER` (validate-review-dir.py:79) exactly, including
`×` and `'`. Row-ID prefixes come from `ROSTER_PREFIX` (:113):
`DCS DL CTL CVI EPW SMM MHM TDO FPM ACS TER ML PSI AL SPC IFC STB CAS TAS CLP
DRY TSY OBL MIS PRS PLS BAG PAT AXI NET FTS HOL`, plus `GSS` and `GAI` for the
two `GENERALIST_ROSTER` threads (:147, :164). The ten specialist lenses are
`SPECIALIST_LENSES` (:151).

---
