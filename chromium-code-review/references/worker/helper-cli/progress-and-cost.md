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

## Progress and cost

```
log-progress.py  <review-dir> spawned   <WORK_ID> <attempt> [text]
log-progress.py  <review-dir> collected <WORK_ID> <attempt> <text>
log-progress.py  <review-dir> phase     <label> <text>
log-progress.py  <review-dir> note      <text>

report-review-costs.py <review-dir>
archive-review-instrumentation.py [--canonical-skill-dir DIR] [--version V] <review-dir>
instrument-command.py [--cwd CWD] <review-dir> <work_id> <attempt> -- <command> [args...]
```

The cost report derives all wall-clock evidence from `progress.md`, so
spawn/collect/phase events must go through `log-progress.py`, which stamps UTC
itself and validates the shape. Work IDs are opaque whitespace-free tokens.
