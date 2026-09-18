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

## Waiting for workers

```
await-workers.py [-h] [--work WORK_ID[:ATTEMPT]] [--timeout-seconds N]
                 [--poll-seconds N] [--heartbeat TEXT] [--no-heartbeat]
                 [--validate | --no-validate] [--no-transition] [--quiet]
                 review_dir
```

One blocking call that returns when the wave is done. Defaults: timeout 5400 s,
poll 30 s (both accept floats), validation on, state transitions on. `--work`
is repeatable; a bare `WORK_ID` selects its highest sealed attempt. With no
`--work`, the wave is every row in state `running` or `queued`.

While it waits it heartbeats the lease, stats each unit's `artifact`, runs
`validate-worker-artifact.py` at most once per `(path, mtime, size)`,
transitions satisfied units to `complete`, and appends the `collected` event to
`progress.md`. A heartbeat failure is reported in the summary and never aborts
the wait. It prints one line per unit, never artifact contents.

| Exit | Meaning | Do next |
| --- | --- | --- |
| 0 | every unit satisfied | proceed to the next phase |
| 2 | timeout, units still outstanding | inspect the named units; respawn or mark `retryable` |
| 3 | all finished, at least one `needs-repair` | repair or respawn the named units |

An empty wave prints `await-workers.py: nothing outstanding` and exits 0.

`CHROMIUM_REVIEW_ARTIFACT_VALIDATOR` overrides the validator command (shlex
split, invoked as `<cmd> <review-dir> <artifact>`); it exists for tests.
