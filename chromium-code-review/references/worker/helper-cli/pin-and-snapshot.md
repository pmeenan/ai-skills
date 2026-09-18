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

## Pin and snapshot

```
fetch-cl.sh <CL> [patchset] [review-dir] [--holder KEY] [--force-restart]
snapshot-skill.py [-h] [--check] skill_dir review_dir
```

`fetch-cl.sh` probes the review directory for `chmod` support before doing any
network or git work, because an x20/FUSE review directory cannot hold the
authenticated lease state and the failure would otherwise arrive only after the
expensive fetch. Keep the review directory on local disk:
`/tmp/cl-<CL>-ps<PS>-<holder>`.

On the first pin it writes `pin.md`, `detail.json`, `comments.json`, and
`lease-state.json`; a resume on the same CL/patchset/revision verifies them and
rewrites only the lease state.

`snapshot-skill.py` writes the immutable snapshot at
`<review-dir>/skill-snapshot` and verifies its manifest before reuse; `--check`
verifies without writing.
