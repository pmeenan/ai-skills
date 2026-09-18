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

## Enumerations

Every value below was read from the scripts' own argparse definitions. A value
not in these tables is rejected outright.

| Enum | Legal values |
| --- | --- |
| `validate-review-dir.py --phase` | `auto`, `pin`, `collection`, `verification`, `reconciliation`, `final` |
| `validate-worker-artifact.py --kind` | `auto`, `inventory`, `plan`, `ledger`, `verdict`, `affinity`, `generic` |
| `seal-work-unit.py --tier` | `frontier`, `inherit`, `mechanical`, `standard` |
| subagent `Model` (check harness; Jetski default / Opus fallback) | `frontier` $\rightarrow$ `inherit` (`pro`/`opus`), `standard` $\rightarrow$ `flash` (`sonnet`), `mechanical` $\rightarrow$ `flash_lite` (`haiku`) |
| `seal-work-unit.py --input ROLE=` | `control`, `reference`, `assigned`, `candidate-packet`, `card`, `frame`, `section`, `prestate` |
| orchestration `state` | `queued`, `running`, `partial`, `retryable`, `needs-repair`, `complete`, `terminated` |
| `worktree-lease.py` subcommands | `acquire`, `write-state`, `validate-state`, `heartbeat`, `release`, `release-token`, `check`, `holder-of`, `holders`, `gc` |
| `log-progress.py` events | `spawned`, `collected`, `phase`, `note` |

There is no `list`, `status`, or `progress` lease subcommand; peers are
enumerated with `holders`, this review's own holder with `holder-of`.
There is no `inventory`, `planning`, or `discovery` validator phase; discovery
work validates under `collection`.
