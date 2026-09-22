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

## Authenticated output history

```
archive-output-version.py <review-dir> <absolute-output-path> <historical-bytes-file>
```

Before revising a collected direct child of `draft-parts`, `gerrit-parts`, or
`output-coverage`, or the top-level `draft-review.md`, `gerrit-comments.md`, or
`output-coverage.tsv`, archive its old bytes with this helper (the current file itself may be
the historical-bytes input). The bytes must exactly match an existing input
manifest binding for that path. Archives are read-only, content-addressed
files under `output-history/`; an already revised version can be restored
there only when its recovered bytes match the original recorded size/hash.
The gate may authenticate historical input/prestate rows against this archive
without rehashing those old rows. Current output coverage and validation still
check the current files. This exception never applies to ledgers or other
append-only artifacts.
The named revision copies required by the output revision contract still
must be preserved; this authenticated archive supplements those copies.
