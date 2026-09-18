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

## Mutating work-unit state

```
set-work-state.py [-h] [--task-id TASK_ID] [--remaining-scope REMAINING_SCOPE]
                  [--note NOTE] [--log] [--force]
                  review_dir work_id attempt
                  {queued,running,partial,retryable,needs-repair,complete,terminated}
```

Changes the `state` of exactly one row — plus `task_id` / `remaining_scope` if
asked — and leaves every other byte of the file alone. Setting a row to the
state it already holds succeeds and prints `already <state>`. Transitions out
of `complete` or `terminated` require `--force`. `--log` also appends the
matching `progress.md` event (`complete` → `collected`, `running` → `spawned`,
otherwise `note`) and heartbeats the lease.
