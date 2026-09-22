<!-- Generated from ../../helper-cli.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Helper CLI Reference

**Never read or grep a helper script's source to work out how to call it.**
Look it up here. If an invocation you need is missing, adding it here is part
of doing the work.

For what an *error message* means, do not read
[gate-errors.md](gate-errors.md) either — it is a 700-row lookup table. Query
it instead:

```sh
<skill-dir>/scripts/explain-gate-error.py "<the message you saw>"
```

Paste the message verbatim; concrete paths, line numbers, and quoted values
are ignored when matching. `--max N` widens the result set. Exit 1 means no
row matched, and the corrective action is to add one once you know the fix.

> Measured over 31 runs of this skill, orchestrators opened helper source 725
> times — `validate-review-dir.py` alone 149 times across 8 conversations —
> and ran roughly 91 `--help` probes, purely to recover facts that are on this
> page.

Throughout, `<skill-dir>` means the sealed snapshot at
`<review-dir>/skill-snapshot`, not the canonical checkout, from the moment
`snapshot-skill.py` has run.

## Materialization and indexes

```
build-review-indexes.py [--output-dir DIR] [--check] <review-dir>
build-caller-index.py --worktree W --revision R [--pathspec P] <review-dir>
build-scope-packets.py --worktree W --parent P --revision R [--spec SPEC] [--output OUT] <review-dir> <work_id>
build-discovery-brief.py --work-id ID [--attempt N] --entry E --procedure P [--pathspec SPEC] [--output OUT] <review-dir>
build-batch-briefs.py --phase {verification,root-cause} [--attempt N] [--round R] [--seal] <review-dir>
```

Run `build-scope-packets.py` (or `build-batch-briefs.py` for Phase 5 `V*` and
Phase 5.5 `RC*` batches) before sealing, so the scoped code packet and generated
briefs are deterministic, hashable inputs rather than hand-crafted by planner
subagents.

`build-batch-briefs.py` reads the canonical `## Batches` tables in the
verification/root-cause templates. Root-cause membership uses
`root families / scopes`; legacy generator headings and `items` remain accepted.
Malformed, missing, duplicate, or zero-row schedules fail instead of reporting
successful zero rendering. Do not invoke it for the separately validated empty
fast paths, which have no worker briefs to create. Existing batches and briefs
must not be regenerated while workers are active or their inputs are sealed.

For root-cause batches containing provisional merge aliases,
`build-batch-briefs.py` adds a bounded `packets/RC*-merge-context.md` input with
exact proposed chains, effective comparison candidates/descriptors, and each
ultimate survivor's unique verdict, trace closures, and verified affinity.
This is supporting comparison evidence, not additional assigned work or
accepted equivalence; a refuted survivor does not refute its alias. Missing or
cyclic targets, ambiguous/missing verdict context, and packet-budget overflow
fail generation. Split complete comparison units rather than truncating them.
